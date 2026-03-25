"""
LLM Adapter — единый интерфейс для работы с разными LLM провайдерами.
Включает retry логику (tenacity), подсчёт токенов и опциональный кэш.
"""
import json
import logging
from typing import Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from agents.core.base_agent import LLMConfig, LLMProvider, CacheProtocol
from agents.core.llm.engines.base_engine import BaseLLMEngine
from agents.core.llm.engines.openai_engine import OpenAIEngine
from agents.core.llm.engines.claude_engine import ClaudeEngine
from agents.core.llm.engines.gemini_engine import GeminiEngine


logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class LLMAdapter:
    """Единый интерфейс для работы с разными LLM провайдерами."""

    def __init__(self, config: LLMConfig, cache: Optional[CacheProtocol] = None):
        """
        Args:
            config: конфигурация LLM
            cache: экземпляр, реализующий CacheProtocol (опционально)
        """
        self.config = config
        self.cache = cache
        self.engine: Optional[BaseLLMEngine] = self._init_engine()
        self.tokens_used: int = 0
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

        return engine_class(self.config)

    # ── public ────────────────────────────────────────────────────

    def call(self, prompt: str) -> str:
        """
        Основной метод вызова LLM.
        Проверяет кэш → вызывает engine с retry → сохраняет в кэш.
        """
        # Проверяем кэш
        if self.cache:
            cached = self.cache.get(prompt)
            if cached is not None:
                logger.debug("Ответ получен из кэша")
                return cached

        # Mock режим
        if self.config.provider == LLMProvider.MOCK:
            return self._call_mock(prompt)

        # Вызов с retry
        response = self._call_with_retry(prompt)

        # Сохраняем в кэш
        if self.cache:
            self.cache.set(prompt, response)

        return response

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call_with_retry(self, prompt: str) -> str:
        """Вызов engine с retry логикой через tenacity."""
        assert self.engine is not None, "Engine не инициализирован"
        response, tokens = self.engine.call(prompt)
        self.tokens_used += tokens
        return response

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
        return self.tokens_used

    def reset_tokens(self) -> None:
        """Сбрасывает счётчик токенов."""
        self.tokens_used = 0