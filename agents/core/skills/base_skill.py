"""
Базовый класс для навыков (skills) агентов.

TODO (v0.2):
    - Определить интерфейс Skill (input/output typing)
    - Composable skills pipeline
    - Интеграция с AgentFactory
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseSkill(ABC):
    """
    Абстрактный навык агента.

    Skill — переиспользуемый блок логики,
    который агент может вызывать в процессе выполнения.
    """

    @abstractmethod
    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError