"""
Фабрика для создания агентов.
Делегирует хранение классов в Registry (единый источник правды).
"""
import logging
from typing import List, Optional, Type

from agents.core.base_agent import AgentConfig, BaseAgent, LLMAdapterProtocol


logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Фабрика для создания агентов.

    Не хранит классы самостоятельно — делегирует в Registry.
    Registry = единый источник правды для метаданных И классов.
    """

    def __init__(
        self,
        registry: "AgentRegistry",
        validator: Optional["AgentValidator"] = None,
    ) -> None:
        """
        Args:
            registry: реестр метаданных и классов агентов (обязателен)
            validator: валидатор совместимости (опционально;
                       если не передан — создаётся автоматически)
        """
        self._registry = registry
        self._validator = validator

        if self._validator is None:
            from agents.core.agent_validator import AgentValidator
            self._validator = AgentValidator(self._registry)

        logger.info(
            "Factory создана: %d агентов в registry, %d с привязанным классом",
            len(self._registry.list_agents()),
            len(self._registry.list_bound_agents()),
        )

    # ── регистрация (делегирует в registry) ───────────────────────

    def register(self, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Регистрирует класс агента в registry.

        Если метаданные уже есть — привязывает класс.
        Если нет — создаёт минимальные метаданные автоматически.

        Raises:
            TypeError: если agent_class не наследник BaseAgent
        """
        self._registry.bind_class(agent_type, agent_class)

    def register_agent(self, agent_type: str):
        """Декоратор для автоматической регистрации агента."""
        def decorator(cls: Type[BaseAgent]) -> Type[BaseAgent]:
            self.register(agent_type, cls)
            return cls
        return decorator

    def unregister(self, agent_type: str) -> None:
        """Удаляет агента из реестра."""
        self._registry.unregister(agent_type)

    # ── создание ──────────────────────────────────────────────────

    def create_agent(
        self,
        agent_type: str,
        config: AgentConfig,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
        *,
        skip_validation: bool = False,
    ) -> BaseAgent:
        """
        Создаёт агента нужного типа.

        Args:
            agent_type: строковый идентификатор
            config: конфигурация агента
            llm_adapter: LLM адаптер (опционально)
            skip_validation: пропустить валидацию

        Raises:
            ValueError: тип не зарегистрирован, класс не привязан,
                        или валидация не пройдена
        """
        # Получаем класс из registry
        agent_class = self._registry.get_class(agent_type)
        if agent_class is None:
            available = self._registry.list_bound_agents()
            if agent_type not in self._registry:
                raise ValueError(
                    f"Неизвестный тип агента: '{agent_type}'. "
                    f"Доступные (с классом): {available}"
                )
            raise ValueError(
                f"Агент '{agent_type}' зарегистрирован в registry, "
                f"но класс не привязан. Вызовите factory.register('{agent_type}', MyAgentClass)"
            )

        # Валидация (если validator подключён)
        if not skip_validation and self._validator is not None:
            validation = self._validator.validate(agent_type, config)
            if not validation.is_valid:
                errors_str = "; ".join(
                    f"[{e.code}] {e.message}" for e in validation.errors
                )
                raise ValueError(
                    f"Валидация агента '{agent_type}' не пройдена: {errors_str}"
                )
            logger.debug("Валидация агента '%s' пройдена", agent_type)

        return agent_class(config, llm_adapter)

    # ── информация ────────────────────────────────────────────────

    def list_agents(self) -> List[str]:
        """Список агентов с привязанным классом (готовых к созданию)."""
        return self._registry.list_bound_agents()

    def list_all_agents(self) -> List[str]:
        """Список всех агентов в registry (включая без класса)."""
        return self._registry.list_agents()

    def get_agent_info(self, agent_type: str) -> Optional[str]:
        """Описание агента из registry."""
        return self._registry.format_info(agent_type)