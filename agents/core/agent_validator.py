"""
Валидатор совместимости агента с конфигурацией.
Единственная ответственность — проверка ограничений.
"""
import logging
from typing import List

from agents.core.base_agent import AgentConfig
from agents.agent_registry import AgentRegistry, AgentMetadata


logger = logging.getLogger(__name__)


class AgentValidator:
    """Проверяет, может ли агент работать с заданной конфигурацией."""

    def __init__(self, registry: AgentRegistry):
        self._registry = registry

    def validate(self, agent_type: str, config: AgentConfig) -> bool:
        """Полная проверка: провайдер + наличие в реестре."""
        metadata = self._registry.get(agent_type)
        if metadata is None:
            logger.warning("Агент '%s' не найден в реестре", agent_type)
            return False

        errors = self._collect_errors(agent_type, metadata, config)
        for err in errors:
            logger.warning(err)
        return len(errors) == 0

    def _collect_errors(
        self,
        agent_type: str,
        metadata: AgentMetadata,
        config: AgentConfig,
    ) -> List[str]:
        """Собирает список ошибок валидации (расширяемо)."""
        errors: List[str] = []

        # проверка провайдера
        if metadata.supported_providers:
            provider = config.llm_config.provider.value
            if provider not in metadata.supported_providers:
                errors.append(
                    f"Агент '{agent_type}' не поддерживает провайдера '{provider}'. "
                    f"Допустимые: {metadata.supported_providers}"
                )

        return errors