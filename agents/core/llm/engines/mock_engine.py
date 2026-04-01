"""Mock engine для тестирования без внешних API-вызовов."""

import json
import logging

from agents.core.llm.engines.base_engine import BaseLLMEngine, LLMResponse

logger = logging.getLogger(__name__)


class MockEngine(BaseLLMEngine):
    """
    Возвращает фиксированный JSON-ответ.
    Используется при LLM_PROVIDER=mock.
    """

    def call(self, prompt: str) -> LLMResponse:
        logger.debug("MOCK вызов: %s...", prompt[:100])
        return LLMResponse(
            text=json.dumps({
                "reason_short": "Mock reason",
                "reason_long": "This is a mock response for testing",
                "confidence": 1.0,
            }),
            tokens_used=0,
            model="mock",
        )

    async def acall(self, prompt: str) -> LLMResponse:
        return self.call(prompt)