"""
Базовый класс для инструментов (tools) агентов.

TODO (v0.2):
    - Tool = внешний вызов (API, DB, вычисление)
    - Определить интерфейс: name, description, execute()
    - Tool registry для автоматического подключения к агентам
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """
    Абстрактный инструмент агента.

    Tool — внешний вызов, который агент может использовать
    для получения данных или выполнения действий.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @abstractmethod
    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError