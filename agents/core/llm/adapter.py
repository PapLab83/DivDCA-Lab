"""
LLM Adapter — единый интерфейс для работы с разными LLM провайдерами.
Включает retry логику (tenacity), подсчёт токенов и опциональный кэш.
"""
import hashlib
import json
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
from agents.core.llm.exceptions import LLMTransientError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class LLMAdapter:
    """Единый интерфейс для работы с разными LLM провайдерами."""

    def __init__(
        self,
        config: LLMConfig,
        api_config: Optional[ApiConfig] = None,
        cache: Optional[CacheProtocol] = None,
    ):
        """
        Args:
            config: конфигурация LLM (из base_agent.py)
            api_config: конфигурация API-подключения (ключ, base_url)
            cache: экземпляр, реализующий CacheProtocol (опционально)
        """
        self.config = config
        self.api_config = api_config or ApiConfig()
        self.cache = cache
        self.engine: Optional[BaseLLMEngine] = self._init_engine()
        self._tokens_used: int = 0
        self._lock = threading.Lock()
        logger.debug("LLMAdapter инициализирован с провайдером %s", config.provider)

    def _init_engine(self) -> Optional[BaseLLMEngine]:
        """Инициализирует нужный engine по провайдеру."""
        engines = {
            LLMProvider.OPENAI: OpenAIEngine,
            LLMProvider.CLAUDE: ClaudeEngine,
            LLMProvider.GEMINI: GeminiEngine,
        }

        if self.config.provider == LLMProvider.MOCK:
            return None

        engine_class = engines.get(self.config.provider)
        if not engine_class:
            raise ValueError(f"Неизвестный провайдер: {self.config.provider}")

        return engine_class(self.config, self.api_config)

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _cache_key(prompt: str) -> str:
        """Генерирует компактный ключ кэша из промпта."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    # ── public ────────────────────────────────────────────────────

    def call(self, prompt: str) -> str:
        """
        Основной метод вызова LLM.
        Проверяет кэш → вызывает engine/mock → сохраняет в кэш.

        Returns:
            Текст ответа от LLM
        """
        # Проверяем кэш
        if self.cache:
            key = self._cache_key(prompt)
            cached = self.cache.get(key)
            if cached is not None:
                logger.debug("Ответ получен из кэша")
                return cached

        # Получаем ответ (mock или реальный engine)
        if self.config.provider == LLMProvider.MOCK:
            response = self._call_mock(prompt)
        else:
            response = self._call_with_retry(prompt)

        # Сохраняем в кэш
        if self.cache:
            key = self._cache_key(prompt)
            self.cache.set(key, response)

        return response

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(LLMTransientError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call_with_retry(self, prompt: str) -> str:
        """
        Вызов engine с retry логикой через tenacity.

        Returns:
            Текст ответа (str), токены учитываются внутри.
        """
        if self.engine is None:
            raise RuntimeError(
                f"Engine не инициализирован для провайдера {self.config.provider}"
            )

        try:
            llm_response: LLMResponse = self.engine.call(prompt)
        except LLMTransientError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Неожиданная ошибка LLM: {exc}") from exc

        with self._lock:
            self._tokens_used += llm_response.tokens_used

        return llm_response.text

    def _call_mock(self, prompt: str) -> str:
        """Mock ответ для тестирования."""
        logger.debug("MOCK вызов с промптом: %s...", prompt[:100])
        return json.dumps({
            "reason_short": "Mock reason",
            "reason_long": "This is a mock response for testing",
            "confidence": 1.0,
        })

    def get_tokens_used(self) -> int:
        """Возвращает суммарное количество использованных токенов."""
        with self._lock:
            return self._tokens_used

    def reset_tokens(self) -> None:
        """Сбрасывает счётчик токенов."""
        with self._lock:
            self._tokens_used = 0