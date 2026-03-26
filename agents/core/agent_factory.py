"""
Фабрика для создания агентов.
Поддерживает ручную регистрацию и декоратор @register_agent.
"""
import logging
import threading
from typing import Dict, List, Optional, Type

from agents.core.base_agent import AgentConfig, BaseAgent, LLMAdapterProtocol


logger = logging.getLogger(__name__)


class AgentFactory:
    """Фабрика для создания агентов (потокобезопасная, singleton)."""

    _instance: Optional["AgentFactory"] = None
    _init_lock = threading.Lock()

    # ── singleton ─────────────────────────────────────────────────

    def __new__(cls) -> "AgentFactory":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Инициализируем только один раз
        if hasattr(self, "_agents"):
            return
        self._agents: Dict[str, Type[BaseAgent]] = {}
        self._lock = threading.Lock()

    @classmethod
    def _reset(cls) -> None:
        """
        Сбрасывает singleton. Только для тестов.
        После вызова следующий AgentFactory() создаст новый экземпляр.
        """
        with cls._init_lock:
            cls._instance = None

    # ── регистрация ───────────────────────────────────────────────

    def register(self, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Регистрирует новый тип агента.

        Args:
            agent_type: строковый идентификатор (например, 'event_generation')
            agent_class: класс агента, наследующий BaseAgent

        Raises:
            TypeError: если agent_class не наследник BaseAgent
        """
        if not issubclass(agent_class, BaseAgent):
            raise TypeError(f"{agent_class.__name__} должен быть наследником BaseAgent")

        with self._lock:
            if agent_type in self._agents:
                existing = self._agents[agent_type].__name__
                logger.warning(
                    "Тип агента '%s' уже зарегистрирован (%s), перезаписывается на %s",
                    agent_type,
                    existing,
                    agent_class.__name__,
                )
            self._agents[agent_type] = agent_class
            logger.debug(
                "Зарегистрирован тип агента: %s -> %s", agent_type, agent_class.__name__
            )

    def register_agent(self, agent_type: str):
        """
        Декоратор для автоматической регистрации агента.

        Пример::

            @factory.register_agent("event_generation")
            class EventGenerationAgent(BaseAgent):
                ...
        """
        def decorator(cls: Type[BaseAgent]) -> Type[BaseAgent]:
            self.register(agent_type, cls)
            return cls
        return decorator

    def unregister(self, agent_type: str) -> None:
        """Удаляет агента из реестра (полезно в тестах)."""
        with self._lock:
            self._agents.pop(agent_type, None)

    # ── создание ──────────────────────────────────────────────────

    def create_agent(
        self,
        agent_type: str,
        config: AgentConfig,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
    ) -> BaseAgent:
        """
        Создаёт агента нужного типа.

        Raises:
            ValueError: если тип агента не зарегистрирован
        """
        with self._lock:
            if agent_type not in self._agents:
                raise ValueError(
                    f"Неизвестный тип агента: {agent_type}. "
                    f"Доступные: {list(self._agents.keys())}"
                )
            agent_class = self._agents[agent_type]
        return agent_class(config, llm_adapter)

    # ── информация ────────────────────────────────────────────────

    def list_agents(self) -> List[str]:
        """Возвращает список всех зарегистрированных типов агентов."""
        with self._lock:
            return list(self._agents.keys())


# Глобальный экземпляр фабрики (singleton)
default_factory = AgentFactory()
register_agent = default_factory.register_agent