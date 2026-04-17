"""Mock engine для тестирования без внешних API-вызовов."""

import json
import logging
import re

from agents.core.llm.engines.base_engine import BaseLLMEngine, LLMResponse

logger = logging.getLogger(__name__)


# Реестр mock-ответов по ключевым словам в промпте.
# Добавляй новые задачи сюда при появлении новых агентов.
_MOCK_RESPONSES: dict[str, dict] = {
    "event_generation": {
        "reason_short": "Mock: dividend policy change",
        "reason_long": (
            "Mock response for event_generation task. "
            "The company adjusted its dividend policy based on mock financial conditions."
        ),
        "confidence": 0.75,
    },
    "event_scoring": {
        "score": 0.8,
        "feedback": "Mock feedback: event is relevant",
        "suggestions": "Mock suggestion: consider macro context",
    },
    "event_validation": {
        "score": 0.7,
        "feedback": "Mock validation feedback",
        "suggestions": "Mock: no critical issues found",
    },
    "financial_analysis": {
        "summary": "Mock financial analysis summary",
        "recommendation": "hold",
        "confidence": 0.65,
    },
    # Fallback — используется если задача не распознана
    "_default": {
        "result": "mock_default_response",
        "confidence": 0.5,
        "note": "MockEngine: task not recognized, using default response",
    },
}

# Ключевые слова для определения задачи из промпта.
# Порядок важен: более специфичные паттерны — выше.
_TASK_PATTERNS: list[tuple[str, str]] = [
    (r"event.{0,20}generat|dividend.*change|reason_short", "event_generation"),
    (r"event.{0,20}scor|score.*feedback|suggestions", "event_scoring"),
    (r"event.{0,20}valid|validate.*description", "event_validation"),
    (r"financial.{0,20}analys|recommendation.*hold|buy|sell", "financial_analysis"),
]


def _detect_task(prompt: str) -> str:
    """
    Определяет тип задачи по содержимому промпта.

    Проверяет паттерны в порядке приоритета.
    Возвращает '_default' если задача не распознана.
    """
    lowered = prompt.lower()
    for pattern, task_name in _TASK_PATTERNS:
        if re.search(pattern, lowered):
            logger.debug("MockEngine: detected task '%s'", task_name)
            return task_name

    logger.debug(
        "MockEngine: task not detected from prompt (first 100 chars: %r), using default",
        prompt[:100],
    )
    return "_default"


class MockEngine(BaseLLMEngine):
    """
    Prompt-aware mock engine для тестирования без внешних API-вызовов.

    Определяет тип задачи из содержимого промпта и возвращает
    соответствующий структурированный JSON-ответ.

    Это позволяет тестировать агентов с разными задачами изолированно,
    не получая одинаковый ответ вне зависимости от промпта.

    Используется при LLM_PROVIDER=mock.
    """

    def call(self, prompt: str) -> LLMResponse:
        task = _detect_task(prompt)
        response_data = _MOCK_RESPONSES.get(task, _MOCK_RESPONSES["_default"])

        logger.debug("MockEngine.call: task=%s, prompt_len=%d", task, len(prompt))

        return LLMResponse(
            text=json.dumps(response_data, ensure_ascii=False),
            tokens_used=0,
            model="mock",
            finish_reason="stop",
        )

    async def acall(self, prompt: str) -> LLMResponse:
        """Async версия — делегирует синхронному call."""
        return self.call(prompt)