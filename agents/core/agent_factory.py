import logging

from typing import Dict, List, Optional, Type

from base_agent import (
    AgentConfig,
    BaseAgent,
    LLMAdapterProtocol,
)


logger = logging.getLogger(__name__)


class AgentFactory:
    """Фабрика для создания агентов"""

    def __init__(self):
        self._agents: Dict[str, Type[BaseAgent]] = {}

    def register(self, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Регистрирует новый тип агента.

        Args:
            agent_type: строковый идентификатор агента (например, 'event_generation')
            agent_class: класс агента, наследующий BaseAgent
        """
        if not issubclass(agent_class, BaseAgent):
            raise TypeError(f"{agent_class.__name__} должен быть наследником BaseAgent")
        self._agents[agent_type] = agent_class
        logger.debug(f"Зарегистрирован тип агента: {agent_type} -> {agent_class.__name__}")

    def create_agent(
        self,
        agent_type: str,
        config: AgentConfig,
        llm_adapter: Optional[LLMAdapterProtocol] = None
    ) -> BaseAgent:
        """
        Создаёт агента нужного типа.

        Args:
            agent_type: строковый идентификатор агента
            config: конфигурация для агента
            llm_adapter: адаптер для LLM

        Returns:
            экземпляр агента

        Raises:
            ValueError: если тип агента не зарегистрирован
        """
        if agent_type not in self._agents:
            raise ValueError(
                f"Неизвестный тип агента: {agent_type}. "
                f"Доступные: {list(self._agents.keys())}"
            )
        agent_class = self._agents[agent_type]
        return agent_class(config, llm_adapter)

    def list_agents(self) -> List[str]:
        """Возвращает список всех зарегистрированных типов агентов"""
        return list(self._agents.keys())

    def unregister(self, agent_type: str) -> None:
        """Удаляет агента из реестра (полезно в тестах)"""
        self._agents.pop(agent_type, None)