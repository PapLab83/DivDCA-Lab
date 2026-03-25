"""
Реестр метаданных агентов.
Хранит описание, версию, входные/выходные данные каждого агента.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from agents.core.base_agent import AgentConfig


logger = logging.getLogger(__name__)


@dataclass
class AgentMetadata:
    """Метаданные агента"""
    name: str
    description: str
    version: str
    inputs: List[str]
    outputs: List[str]
    prompt_components: List[str] = field(default_factory=list)
    supported_providers: List[str] = field(default_factory=list)


class AgentRegistry:
    """
    Реестр всех доступных агентов.
    Хранит метаданные о каждом агенте.
    """

    def __init__(self, load_defaults: bool = True):
        self._agents: Dict[str, AgentMetadata] = {}
        if load_defaults:
            self._load_defaults()

    def _load_defaults(self) -> None:
        """Загружает метаданные агентов по умолчанию."""
        defaults = {
            "event_generation": AgentMetadata(
                name="Event Generation Agent",
                description="Генерирует описания событий на основе исторических данных",
                version="0.1.0",
                inputs=["ticker", "year", "price", "dividend", "yoy_change"],
                outputs=["reason_short", "reason_long", "confidence"],
                prompt_components=["system", "instruction", "examples", "format", "constraints"],
            ),
            "event_validation": AgentMetadata(
                name="Event Validation Agent",
                description="Проверяет и оценивает сгенерированные описания",
                version="0.1.0",
                inputs=["ticker", "year", "generated_text"],
                outputs=["score", "feedback", "suggestions"],
                prompt_components=["system", "instruction", "format"],
            ),
        }
        self._agents.update(defaults)

    # ── CRUD ──────────────────────────────────────────────────────

    def register(self, agent_type: str, metadata: AgentMetadata) -> None:
        """Регистрирует метаданные агента."""
        self._agents[agent_type] = metadata
        logger.debug("Зарегистрированы метаданные для агента: %s", agent_type)

    def get(self, agent_type: str) -> Optional[AgentMetadata]:
        """Возвращает метаданные агента или None."""
        return self._agents.get(agent_type)

    def list_agents(self) -> List[str]:
        """Список всех зарегистрированных агентов."""
        return list(self._agents.keys())

    # ── отображение ───────────────────────────────────────────────

    def format_info(self, agent_type: str) -> str:
        """Возвращает human-readable описание агента."""
        metadata = self.get(agent_type)
        if metadata is None:
            return f"Агент '{agent_type}' не найден"
        lines = [
            f"Агент: {metadata.name}",
            f"Версия: {metadata.version}",
            f"Описание: {metadata.description}",
            f"Входные данные: {', '.join(metadata.inputs)}",
            f"Выходные данные: {', '.join(metadata.outputs)}",
        ]
        return "\n".join(lines)

    # ── валидация ─────────────────────────────────────────────────

    def validate_agent(self, agent_type: str, config: AgentConfig) -> bool:
        """Проверяет, может ли агент работать с заданной конфигурацией."""
        metadata = self.get(agent_type)
        if not metadata:
            return False
        if metadata.supported_providers:
            if config.llm_config.provider.value not in metadata.supported_providers:
                logger.warning(
                    "Агент %s не поддерживает провайдера %s",
                    agent_type, config.llm_config.provider,
                )
                return False
        return True