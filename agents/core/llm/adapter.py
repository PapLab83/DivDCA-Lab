"""
LLM Adapter — единый интерфейс для работы с разными LLM провайдерами.
Включает retry логику (tenacity), подсчёт токенов и опциональный кэш.
"""
import hashlib
import logging
import threading
from typing import Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from agents.core.base_agent import ApiConfig, LLMConfig, LLMProvider, CacheProtocol
from agents.core.llm.engines.base_engine import BaseLLMEngine, LLMResponse
from agents.core.llm.engines.openai_engine import OpenAIEngine
from agents.core.llm.engines.claude_engine import ClaudeEngine
from agents.core.llm.engines.gemini_engine import GeminiEngine
from agents.core.llm.engines.mock_engine import MockEngine
from agents.core.llm.exceptions import LLMTransientError

logger = logging.getLogger(__name__)


class LLMAdapter:
    """
    Единый интерфейс для работы с разными LLM провайдерами.

    Ответственности:
        - выбор engine по провайдеру
        - retry с exponential backoff (только LLMTransientError)
        - кэширование ответов (опционально)
        - подсчёт использованных токенов
    """

    def __init__(
        self,
        config: LLMConfig,
        api_config: Optional[ApiConfig] = None,
        cache: Optional[CacheProtocol] = None,
    ):
        """
        Args:
            config: конфигурация LLM (provider, model, temperature и т.д.)
            api_config: конфигурация API-подключения (ключ, base_url, retries)
            cache: экземпляр, реализующий CacheProtocol (опционально)
        """
        self.config = config
        self.api_config = api_config or ApiConfig()
        self.cache = cache
        self.engine: BaseLLMEngine = self._init_engine()
        self._tokens_used: int = 0
        self._lock = threading.Lock()

        # Retry-обёртки — единственное место определения retry-логики.
        # Параметры берутся из api_config.retries.
        self._call_with_retry = self._make_retry(self._call_engine)
        self._acall_with_retry = self._make_async_retry(self._acall_engine)

        logger.debug(
            "LLMAdapter инициализирован: provider=%s, model=%s, retries=%d",
            config.provider,
            config.model,
            self.api_config.retries,
        )

    # ── engine init ───────────────────────────────────────────────

    def _init_engine(self) -> BaseLLMEngine:
        """Создаёт engine по провайдеру из конфига."""
        engines = {
            LLMProvider.OPENAI: OpenAIEngine,
            LLMProvider.CLAUDE: ClaudeEngine,
            LLMProvider.GEMINI: GeminiEngine,
            LLMProvider.MOCK: MockEngine,
        }

        engine_class = engines.get(self.config.provider)
        if engine_class is None:
            raise ValueError(
                f"Неизвестный провайдер: {self.config.provider}. "
                f"Доступные: {list(engines.keys())}"
            )

        if self.config.provider == LLMProvider.MOCK:
            return engine_class(self.config)

        return engine_class(self.config, self.api_config)

    # ── retry factory ─────────────────────────────────────────────

    def _make_retry(self, fn):
        """
        Оборачивает синхронную функцию retry-логикой.
        Параметры retry берутся из api_config.
        """
        return retry(
            stop=stop_after_attempt(self.api_config.retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(LLMTransientError),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )(fn)

    def _make_async_retry(self, fn):
        """
        Оборачивает асинхронную функцию retry-логикой.
        Tenacity корректно работает с async-функциями.
        """
        return retry(
            stop=stop_after_attempt(self.api_config.retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(LLMTransientError),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )(fn)

    # ── engine calls (без retry, без кэша) ────────────────────────

    def _call_engine(self, prompt: str) -> str:
        """
        Один синхронный вызов engine.
        Retry и кэш — на уровне выше.
        """
        try:
            llm_response: LLMResponse = self.engine.call(prompt)
        except LLMTransientError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Неожиданная ошибка LLM: {exc}") from exc

        self._add_tokens(llm_response.tokens_used)
        return llm_response.text

    async def _acall_engine(self, prompt: str) -> str:
        """
        Один асинхронный вызов engine.
        Retry и кэш — на уровне выше.
        """
        try:
            llm_response: LLMResponse = await self.engine.acall(prompt)
        except LLMTransientError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Неожиданная ошибка LLM: {exc}") from exc

        self._add_tokens(llm_response.tokens_used)
        return llm_response.text

    # ── cache helpers ─────────────────────────────────────────────

    def _cache_key(self, prompt: str) -> str:
        """
        Генерирует ключ кэша из промпта + параметров модели.

        Одинаковый промпт с разными provider/model/temperature
        даёт разные ключи → нет коллизий.
        """
        components = (
            prompt,
            str(self.config.provider),
            self.config.model,
            f"{self.config.temperature:.4f}",
            str(self.config.max_tokens),
        )
        combined = "|".join(components)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _cache_get(self, prompt: str) -> Optional[str]:
        """Проверяет кэш. Возвращает None при отсутствии или если кэш отключён."""
        if self.cache is None:
            return None
        key = self._cache_key(prompt)
        cached = self.cache.get(key)
        if cached is not None:
            logger.debug("Cache hit для промпта (key=%s...)", key[:12])
        return cached

    def _cache_set(self, prompt: str, response: str) -> None:
        """Сохраняет ответ в кэш, если кэш подключён."""
        if self.cache is None:
            return
        key = self._cache_key(prompt)
        self.cache.set(key, response)

    # ── token tracking ────────────────────────────────────────────

    def _add_tokens(self, count: int) -> None:
        """Потокобезопасно добавляет токены к счётчику."""
        with self._lock:
            self._tokens_used += count

    def get_tokens_used(self) -> int:
        """Возвращает суммарное количество использованных токенов."""
        with self._lock:
            return self._tokens_used

    def reset_tokens(self) -> None:
        """Сбрасывает счётчик токенов."""
        with self._lock:
            self._tokens_used = 0

    # ── public: sync ──────────────────────────────────────────────

    def call(self, prompt: str) -> str:
        """
        Синхронный вызов LLM.

        Порядок: cache check → engine call (с retry) → cache save.

        Args:
            prompt: текст промпта

        Returns:
            Текст ответа от LLM

        Raises:
            LLMTransientError: после исчерпания retry
            RuntimeError: engine не инициализирован или неожиданная ошибка
        """
        # Cache check
        cached = self._cache_get(prompt)
        if cached is not None:
            return cached

        # Engine call с retry
        response = self._call_with_retry(prompt)

        # Cache save
        self._cache_set(prompt, response)

        return response

    # ── public: async ─────────────────────────────────────────────

    async def acall(self, prompt: str) -> str:
        """
        Асинхронный вызов LLM.

        Порядок: cache check → async engine call (с retry) → cache save.

        Args:
            prompt: текст промпта

        Returns:
            Текст ответа от LLM

        Raises:
            LLMTransientError: после исчерпания retry
            RuntimeError: engine не инициализирован или неожиданная ошибка
        """
        # Cache check (sync — InMemoryCache потокобезопасный, не блокирует надолго)
        cached = self._cache_get(prompt)
        if cached is not None:
            return cached

        # Async engine call с retry
        response = await self._acall_with_retry(prompt)

        # Cache save
        self._cache_set(prompt, response)

        return response