"""
Переиспользуемые тестовые агенты.
Импортируются в agents/tests/conftest.py и mas/tests/conftest.py.
Единственный источник правды для тестовых реализаций BaseAgent.
"""
from agents.core.base_agent import AgentContext, AgentResult, BaseAgent


class AlwaysSuccessAgent(BaseAgent):
    """Агент, который всегда возвращает успех с фиксированными данными."""

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            success=True,
            data={"message": "ok"},
            prompt_version="test-1.0",
        )


class AlwaysFailAgent(BaseAgent):
    """Агент, который всегда падает с ValueError."""

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        raise ValueError("Тестовая ошибка")


class PartialFailAgent(BaseAgent):
    """
    Агент, который падает на чётных годах.
    Позволяет тестировать смешанные результаты.
    """

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        year = context.metadata.get("year", 0)
        if year % 2 == 0:
            raise RuntimeError(f"Simulated failure for year {year}")
        return AgentResult(
            success=True,
            data={
                "reason_short": f"Reason for {year}",
                "reason_long": f"Detailed reason for year {year}",
                "confidence": 0.8,
            },
        )