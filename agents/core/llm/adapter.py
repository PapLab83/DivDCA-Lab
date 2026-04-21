"""
LLM Adapter — единый интерфейс для работы с разными LLM провайдерами.
Включает retry логику (tenacity), подсчёт токенов и опциональный кэш.
"""

__all__ = [
    "LLMAdapter",
]

import hashlib
import logging
import threading
from typing import Callable, Dict, Optional, Type

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


def _build_default_engine_registry() -> Dict[LLMProvider, Type[BaseLLMEngine]]:
    """
    Строит дефолтный реестр движков.

    Вынесен в функцию чтобы:
    - каждый вызов возвращает новый dict (изоляция между экземплярами)
    - легко переопределять в тестах
    """
    return {
        LLMProvider.OPENAI: OpenAIEngine,
        LLMProvider.CLAUDE: ClaudeEngine,
        LLMProvider.GEMINI: GeminiEngine,
        LLMProvider.MOCK: MockEngine,
    }


class LLMAdapter:
    """
    Единый интерфейс для работы с разными LLM провайдерами.

    Ответственности:
        - выбор engine по провайдеру (через dict-based registry)
        - retry с exponential backoff (только LLMTransientError)
        - кэширование ответов (опционально)
        - подсчёт использованных токенов

    Engine registry (instance-level):
        Каждый экземпляр LLMAdapter имеет собственный изолированный реестр движков.
        Реестр передаётся через конструктор — нет глобального состояния.

        Добавление провайдера через Container (рекомендуется):
            engine_registry = {LLMProvider.CUSTOM: MyCustomEngine}
            container = Container(config, engine_registry=engine_registry)

        Добавление провайдера напрямую (для тестов):
            adapter = LLMAdapter(config, engine_registry={LLMProvider.MOCK: MyMock})

        Добавление провайдера к существующему экземпляру:
            adapter.register_engine_local(LLMProvider.CUSTOM, MyCustomEngine)
    """

    def __init__(
        self,
        config: LLMConfig,
        api_config: Optional[ApiConfig] = None,
        cache: Optional[CacheProtocol] = None,
        engine_registry: Optional[Dict[LLMProvider, Type[BaseLLMEngine]]] = None,
    ):
        """
        Args:
            config: конфигурация LLM (провайдер, модель, температура)
            api_config: конфигурация API (ключ, base_url, retries)
            cache: опциональный кэш (реализует CacheProtocol)
            engine_registry: реестр движков для этого экземпляра.
                Если None — используются дефолтные провайдеры
                    (OpenAI, Claude, Gemini, Mock).
                Если передан — используется как есть (копируется для изоляции).
                Передайте для добавления кастомных провайдеров или
                полного переопределения в тестах:
                    adapter = LLMAdapter(config, engine_registry={LLMProvider.MOCK: MyMock})
        """
        self.config = config
        self.api_config = api_config or ApiConfig()
        self.cache = cache

        # Instance-level registry: полностью изолирован от других экземпляров.
        # Нет глобального состояния — каждый экземпляр независим.
        if engine_registry is not None:
            # Явно переданный registry — копируем для изоляции от мутаций снаружи
            self._engine_registry: Dict[LLMProvider, Type[BaseLLMEngine]] = dict(engine_registry)
        else:
            # Дефолтный registry — новый dict на каждый экземпляр
            self._engine_registry = _build_default_engine_registry()

        self.engine: BaseLLMEngine = self._init_engine()
        self._tokens_used: int = 0
        self._lock = threading.Lock()

        self._call_with_retry = self._make_retry(self._call_engine, is_async=False)
        self._acall_with_retry = self._make_retry(self._acall_engine, is_async=True)

        logger.debug(
            "LLMAdapter инициализирован: provider=%s, model=%s, retries=%d",
            config.provider,
            config.model,
            self.api_config.retries,
        )

    # ── Instance-level registry ───────────────────────────────────

    def register_engine_local(
        self,
        provider: LLMProvider,
        engine_class: Type[BaseLLMEngine],
    ) -> None:
        """
        Регистрирует engine только для этого экземпляра.

        Полезно в тестах для подмены конкретного провайдера
        без влияния на другие экземпляры.

        Args:
            provider: идентификатор провайдера
            engine_class: класс engine (наследник BaseLLMEngine)
        """
        if not issubclass(engine_class, BaseLLMEngine):
            raise TypeError(
                f"{engine_class.__name__} должен быть наследником BaseLLMEngine"
            )
        self._engine_registry[provider] = engine_class
        logger.debug(
            "LLMAdapter: локально зарегистрирован engine %s для провайдера '%s'",
            engine_class.__name__, provider,
        )

    @classmethod
    def list_providers(cls) -> list:
        """Список дефолтных провайдеров."""
        return list(_build_default_engine_registry().keys())

    # ── engine init ───────────────────────────────────────────────

    def _init_engine(self) -> BaseLLMEngine:
        """
        Создаёт engine по провайдеру из instance-level registry.
        """
        engine_class = self._engine_registry.get(self.config.provider)

        if engine_class is None:
            available = list(self._engine_registry.keys())
            raise ValueError(
                f"Неизвестный провайдер: {self.config.provider}. "
                f"Доступные: {available}. "
                f"Добавьте провайдер через Container(engine_registry={{provider: EngineClass}})."
            )

        if self.config.provider == LLMProvider.MOCK:
            return engine_class(self.config)

        return engine_class(self.config, self.api_config)

    # ── retry factory (unified) ───────────────────────────────────

    def _make_retry(self, fn: Callable, *, is_async: bool) -> Callable:
        """
        Единая фабрика retry-обёрток для sync и async функций.
        """
        decorator = retry(
            stop=stop_after_attempt(self.api_config.retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(LLMTransientError),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        wrapped = decorator(fn)
        logger.debug(
            "LLMAdapter: retry настроен для %s (%s, attempts=%d)",
            fn.__name__,
            "async" if is_async else "sync",
            self.api_config.retries,
        )
        return wrapped

    # ── engine calls (без retry, без кэша) ────────────────────────

    def _call_engine(self, prompt: str) -> str:
        """Один синхронный вызов engine."""
        try:
            llm_response: LLMResponse = self.engine.call(prompt)
        except LLMTransientError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Неожиданная ошибка LLM: {exc}") from exc

        self._add_tokens(llm_response.tokens_used)
        return llm_response.text

    async def _acall_engine(self, prompt: str) -> str:
        """Один асинхронный вызов engine."""
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
        """Генерирует ключ кэша из промпта + параметров модели."""
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
        """Проверяет кэш."""
        if self.cache is None:
            return None
        key = self._cache_key(prompt)
        cached = self.cache.get(key)
        if cached is not None:
            logger.debug("Cache hit для промпта (key=%s...)", key[:12])
        return cached

    def _cache_set(self, prompt: str, response: str) -> None:
        """Сохраняет ответ в кэш."""
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
        """
        cached = self._cache_get(prompt)
        if cached is not None:
            return cached

        response = self._call_with_retry(prompt)
        self._cache_set(prompt, response)
        return response

    # ── public: async ─────────────────────────────────────────────

    async def acall(self, prompt: str) -> str:
        """
        Асинхронный вызов LLM.
        Порядок: cache check → async engine call (с retry) → cache save.
        """
        cached = self._cache_get(prompt)
        if cached is not None:
            return cached

        response = await self._acall_with_retry(prompt)
        self._cache_set(prompt, response)
        return response