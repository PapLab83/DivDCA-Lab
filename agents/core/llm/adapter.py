"""
LLM Adapter - единый интерфейс для работы с разными LLM провайдерами.
Берёт на себя retry логику и подсчёт токенов.
Cache подключается через skills/cache.py.
"""

import logging
import time
from typing import Optional

# TODO создать минимально рабочий набор для обкатки
from agents.core.base_agent import LLMConfig, LLMProvider
from agents.core.llm.engines.openai_engine import OpenAIEngine
from agents.core.llm.engines.claude_engine import ClaudeEngine
from agents.core.llm.engines.gemini_engine import GeminiEngine

logger = logging.getLogger(__name__)

# Максимальное количество попыток при ошибке
MAX_RETRIES = 3
# Пауза между попытками в секундах
RETRY_DELAY = 2


class LLMAdapter:
    """Единый интерфейс для работы с разными LLM провайдерами"""

    def __init__(self, config: LLMConfig, cache=None):
        """
        Args:
            config: конфигурация LLM
            cache: экземпляр CacheSkill, опционально
        """
        self.config = config
        self.cache = cache
        self.engine = self._init_engine()
        self.tokens_used: int = 0
        logger.debug(f"LLMAdapter инициализирован с провайдером {config.provider}")

    def _init_engine(self):
        """Инициализирует нужный engine по провайдеру"""
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

    def call(self, prompt: str) -> str:
        """
        Основной метод вызова LLM.
        Включает cache check, retry логику и подсчёт токенов.

        Args:
            prompt: промпт для LLM

        Returns:
            ответ от LLM
        """
        # Проверяем кэш
        if self.cache:
            cached = self.cache.get(prompt)
            if cached:
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

    def _call_with_retry(self, prompt: str) -> str:
        """Вызов engine с retry логикой"""
        last_error: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug(f"Попытка {attempt}/{MAX_RETRIES}")
                response, tokens = self.engine.call(prompt)
                self.tokens_used += tokens
                return response

            except Exception as e:
                last_error = e
                logger.warning(f"Попытка {attempt} неудачна: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        raise RuntimeError(f"Все {MAX_RETRIES} попытки исчерпаны. "
                           f"Последняя ошибка: {last_error}")

    def _call_mock(self, prompt: str) -> str:
        """Mock ответ для тестирования"""
        import json
        logger.debug(f"MOCK вызов с промптом: {prompt[:100]}...")
        return json.dumps({
            "reason_short": "Mock reason",
            "reason_long": "This is a mock response for testing",
            "confidence": 1.0
        })

    def get_tokens_used(self) -> int:
        """Возвращает суммарное количество использованных токенов"""
        return self.tokens_used

    def reset_tokens(self) -> None:
        """Сбрасывает счётчик токенов"""
        self.tokens_used = 0