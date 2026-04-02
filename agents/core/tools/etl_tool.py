"""
Инструмент ETL (Extract-Transform-Load).

TODO (v0.2):
    - Загрузка данных из внешних источников (Yahoo Finance, SEC)
    - Трансформация в формат агентов
    - Кэширование загруженных данных
"""

from agents.core.tools.base_tool import BaseTool
from typing import Any, Dict


class ETLTool(BaseTool):
    """Заглушка. Реализация планируется в v0.2."""

    @property
    def name(self) -> str:
        return "etl"

    @property
    def description(self) -> str:
        return "Загрузка и трансформация данных"

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError("ETLTool ещё не реализован. Планируется в v0.2.")