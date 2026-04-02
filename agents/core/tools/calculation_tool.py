"""
Инструмент для финансовых вычислений.

TODO (v0.2):
    - Расчёт DCA метрик
    - YoY change, CAGR, дивидендная доходность
    - Интеграция с pandas (опционально)
"""

from agents.core.tools.base_tool import BaseTool
from typing import Any, Dict


class CalculationTool(BaseTool):
    """Заглушка. Реализация планируется в v0.2."""

    @property
    def name(self) -> str:
        return "calculation"

    @property
    def description(self) -> str:
        return "Финансовые вычисления (DCA, YoY, CAGR)"

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError("CalculationTool ещё не реализован. Планируется в v0.2.")