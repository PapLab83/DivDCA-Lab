"""
Реестр метаданных агентов.
Хранит описание, версию, входные/выходные данные и класс каждого агента.
Единый источник правды — Factory делегирует хранение классов сюда.
"""

__all__ = [
    "AgentMetadata",
    "AgentNotFoundError",
    "AgentRegistry",
]

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Type

from agents.core.base_agent import BaseAgent


logger = logging.getLogger(__name__)


@dataclass
class AgentMetadata:
    """Метаданные агента."""
    name: str
    description: str
    version: str
    inputs: List[str]
    outputs: List[str]
    prompt_components: List[str] = field(default_factory=list)
    supported_providers: List[str] = field(default_factory=list)
    agent_class: Optional[Type[BaseAgent]] = field(default=None, repr=False)


class AgentNotFoundError(KeyError):
    """Агент не найден в реестре."""


class AgentRegistry:
    """
    Реестр всех доступных агентов.

    Хранит метаданные И (опционально) классы агентов.
    Factory делегирует хранение классов сюда, чтобы избежать
    двойного реестра и рассинхронизации.
    """

    def __init__(self, load_defaults: bool = True):
        self._agents: Dict[str, AgentMetadata] = {}
        self._lock = threading.RLock()
        if load_defaults:
            self._load_defaults()

    # ── загрузка ──────────────────────────────────────────────────

    def _load_defaults(self) -> None:
        """Загружает метаданные из YAML; fallback — встроенный набор."""
        default_path = Path(__file__).parent / "agents_defaults.yaml"
        if default_path.exists():
            self.load_from_file(default_path)
            return

        logger.debug("Файл %s не найден, используются встроенные дефолты", default_path)
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
        with self._lock:
            self._agents.update(defaults)

    def load_from_file(self, path: Path) -> None:
        """Загружает метаданные агентов из YAML-файла."""
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML required for YAML configs: pip install pyyaml"
            ) from None

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Ожидался dict в {path}, получен {type(data).__name__}")
        with self._lock:
            for key, meta in data.items():
                # agent_class не загружается из YAML — только метаданные
                self._agents[key] = AgentMetadata(**meta)
        logger.debug("Загружено %d агентов из %s", len(data), path)

    # ── CRUD ──────────────────────────────────────────────────────

    def register(
        self,
        agent_type: str,
        metadata: AgentMetadata,
    ) -> None:
        """Регистрирует метаданные агента."""
        with self._lock:
            self._agents[agent_type] = metadata
        logger.debug("Зарегистрированы метаданные для агента: %s", agent_type)

    def bind_class(
            self,
            agent_type: str,
            agent_class: Type[BaseAgent],
    ) -> None:
        """
        Привязывает класс агента к существующим метаданным.
        Если метаданных нет — создаёт минимальные автоматически.

        Использует dataclasses.replace для обновления agent_class —
        все остальные поля метаданных сохраняются без явного перечисления.
        Это защищает от ошибок при добавлении новых полей в AgentMetadata.
        """
        from dataclasses import replace as dc_replace

        if not issubclass(agent_class, BaseAgent):
            raise TypeError(
                f"{agent_class.__name__} должен быть наследником BaseAgent"
            )
        with self._lock:
            if agent_type in self._agents:
                # dataclasses.replace: обновляем только agent_class,
                # все остальные поля метаданных сохраняются автоматически.
                self._agents[agent_type] = dc_replace(
                    self._agents[agent_type],
                    agent_class=agent_class,
                )
            else:
                # Автоматические метаданные для агентов без YAML-описания
                self._agents[agent_type] = AgentMetadata(
                    name=agent_class.__name__,
                    description=f"Auto-registered: {agent_class.__name__}",
                    version="0.0.0",
                    inputs=[],
                    outputs=[],
                    agent_class=agent_class,
                )
                logger.warning(
                    "Агент '%s' зарегистрирован без метаданных (auto-generated)",
                    agent_type,
                )
        logger.debug(
            "Привязан класс %s к агенту '%s'",
            agent_class.__name__, agent_type,
        )

    def unregister(self, agent_type: str) -> None:
        """Удаляет агента из реестра."""
        with self._lock:
            if agent_type not in self._agents:
                raise AgentNotFoundError(f"Агент '{agent_type}' не найден в реестре")
            del self._agents[agent_type]
        logger.debug("Удалены метаданные агента: %s", agent_type)

    def get(self, agent_type: str) -> Optional[AgentMetadata]:
        """Возвращает метаданные агента или None."""
        with self._lock:
            return self._agents.get(agent_type)

    def get_or_raise(self, agent_type: str) -> AgentMetadata:
        """Возвращает метаданные или бросает AgentNotFoundError."""
        with self._lock:
            try:
                return self._agents[agent_type]
            except KeyError:
                raise AgentNotFoundError(
                    f"Агент '{agent_type}' не найден в реестре"
                ) from None

    def get_class(self, agent_type: str) -> Optional[Type[BaseAgent]]:
        """Возвращает класс агента или None."""
        with self._lock:
            meta = self._agents.get(agent_type)
            return meta.agent_class if meta else None

    def list_agents(self) -> List[str]:
        """Список всех зарегистрированных агентов."""
        with self._lock:
            return list(self._agents.keys())

    def list_bound_agents(self) -> List[str]:
        """Список агентов с привязанным классом (готовых к созданию)."""
        with self._lock:
            return [
                k for k, v in self._agents.items()
                if v.agent_class is not None
            ]

    def __contains__(self, agent_type: str) -> bool:
        with self._lock:
            return agent_type in self._agents

    # ── отображение ───────────────────────────────────────────────

    def format_info(self, agent_type: str) -> str:
        """Human-readable описание агента."""
        metadata = self.get(agent_type)
        if metadata is None:
            return f"Агент '{agent_type}' не найден"
        lines = [
            f"Агент: {metadata.name}",
            f"Версия: {metadata.version}",
            f"Описание: {metadata.description}",
            f"Входные данные: {', '.join(metadata.inputs)}",
            f"Выходные данные: {', '.join(metadata.outputs)}",
            f"Класс: {metadata.agent_class.__name__ if metadata.agent_class else '<не привязан>'}",
        ]
        return "\n".join(lines)