class AgentFactory:
    """Фабрика для создания агентов"""

    _agents: Dict[str, Type[BaseAgent]] = {}

    @classmethod
    def register(cls, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Регистрирует новый тип агента.

        Args:
            agent_type: строковый идентификатор агента (например, 'event_generation')
            agent_class: класс агента, наследующий BaseAgent
        """
        if not issubclass(agent_class, BaseAgent):
            raise TypeError(f"{agent_class.__name__} должен быть наследником BaseAgent")

        cls._agents[agent_type] = agent_class
        logger.debug(f"Зарегистрирован тип агента: {agent_type} -> {agent_class.__name__}")

    @classmethod
    def create_agent(cls, agent_type: str, config: AgentConfig) -> BaseAgent:
        """
        Создает агента нужного типа.

        Args:
            agent_type: строковый идентификатор агента
            config: конфигурация для агента

        Returns:
            экземпляр агента

        Raises:
            ValueError: если тип агента не зарегистрирован
        """
        if agent_type not in cls._agents:
            raise ValueError(f"Неизвестный тип агента: {agent_type}. "
                             f"Доступные: {list(cls._agents.keys())}")

        agent_class = cls._agents[agent_type]
        return agent_class(config)

    @classmethod
    def list_agents(cls) -> List[str]:
        """Возвращает список всех зарегистрированных типов агентов"""
        return list(cls._agents.keys())