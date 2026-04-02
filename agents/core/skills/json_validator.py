"""
Навык валидации JSON-ответов от LLM по JSON Schema.

TODO (v0.2):
    - Валидация по jsonschema
    - Автоматическая генерация schema из AgentMetadata.outputs
    - Интеграция с BaseAgent._validate_result
"""

from agents.core.skills.base_skill import BaseSkill
from typing import Any, Dict


class JsonValidator(BaseSkill):
    """Заглушка. Реализация планируется в v0.2."""

    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("JsonValidator ещё не реализован. Планируется в v0.2.")