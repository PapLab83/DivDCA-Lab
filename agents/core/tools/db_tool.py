"""
Инструмент для работы с базой данных.

TODO (v0.2):
    - Чтение исторических данных по тикерам
    - Запись результатов агентов
    - Поддержка SQLite / PostgreSQL
"""

from agents.core.tools.base_tool import BaseTool
from typing import Any, Dict


class DBTool(BaseTool):
    """Заглушка. Реализация планируется в v0.2."""

    @property
    def name(self) -> str:
        return "database"

    @property
    def description(self) -> str:
        return "Доступ к базе данных"

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError("DBTool ещё не реализован. Планируется в v0.2.")