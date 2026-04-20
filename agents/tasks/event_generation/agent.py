"""
Агент генерации событий — объясняет причины изменения дивидендов.
"""
import logging
from typing import Set

from agents.core.base_agent import (
    AgentContext,
    AgentConfig,
    AgentResult,
    BaseAgent,
    LLMAdapterProtocol,
    PromptManagerProtocol,
)

logger = logging.getLogger(__name__)


class EventGenerationAgent(BaseAgent):
    """
    Генерирует описание причин изменения дивидендов
    на основе данных тикера за конкретный год.

    Ожидает в context.metadata:
        ticker, year, price, dividend, yoy_change
    """

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        meta = context.metadata

        prompt, version = self._get_prompt(
            context,
            ticker=meta.get("ticker", "UNKNOWN"),
            year=meta.get("year", "N/A"),
            price=meta.get("price", 0),
            dividend=meta.get("dividend", 0),
            yoy_change=meta.get("yoy_change", 0),
        )

        response = self._call_llm(prompt)
        data = self._parse_response(response)

        return AgentResult(
            success=True,
            data=data,
            prompt_version=version,
            llm_response=response,
        )

    def required_fields(self) -> Set[str]:
        return {"reason_short", "reason_long", "confidence"}