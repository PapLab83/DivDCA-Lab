"""
Фабрика для создания агентов.
Делегирует хранение классов в Registry (единый источник правды).
Поддерживает default-зависимости (llm_adapter, prompt_manager),
которые инжектируются автоматически при создании агента.
"""

__all__ = [
    "AgentFactory",
]

import logging
from typing import List, Optional, Type

from agents.core.base_agent import (
    AgentConfig,
    BaseAgent,
    LLMAdapterProtocol,
    PromptManagerProtocol,
)
from agents.core.agent_registry import AgentRegistry
from agents.core.agent_validator import AgentValidator


logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Фабрика для создания агентов.

    Не хранит классы самостоятельно — делегирует в Registry.
    Хранит default-зависимости (llm_adapter, prompt_manager),
    которые пробрасываются в агента если не переданы явно.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        validator: Optional[AgentValidator] = None,
        *,
        default_llm_adapter: Optional[LLMAdapterProtocol] = None,
        default_prompt_manager: Optional[PromptManagerProtocol] = None,
    ) -> None:
        """
        Args:
            registry: реестр метаданных и классов агентов (обязателен)
            validator: валидатор совместимости (опционально;
                       если не передан — создаётся автоматически)
            default_llm_adapter: LLM адаптер по умолчанию
            default_prompt_manager: менеджер промптов по умолчанию
        """
        self._registry = registry
        self._validator = validator or AgentValidator(registry)
        self._default_llm_adapter = default_llm_adapter
        self._default_prompt_manager = default_prompt_manager

        logger.info(
            "Factory создана: %d агентов в registry, %d с привязанным классом, "
            "llm_adapter=%s, prompt_manager=%s",
            len(self._registry.list_agents()),
            len(self._registry.list_bound_agents()),
            type(self._default_llm_adapter).__name__ if self._default_llm_adapter else "None",
            type(self._default_prompt_manager).__name__ if self._default_prompt_manager else "None",
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
        prompt_manager: Optional[PromptManagerProtocol] = None,
        *,
        skip_validation: bool = False,
    ) -> BaseAgent:
        """
        Создаёт агента нужного типа.

        Зависимости разрешаются по приоритету:
            1. Явно переданные аргументы (llm_adapter, prompt_manager)
            2. Default-зависимости из Factory (установлены Container'ом)
            3. None — агент создаётся без адаптера (для тестов)

        Args:
            agent_type: строковый идентификатор
            config: конфигурация агента
            llm_adapter: LLM адаптер (опционально; fallback → default)
            prompt_manager: менеджер промптов (опционально; fallback → default)
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

        # Валидация
        if not skip_validation:
            validation = self._validator.validate(agent_type, config)
            if not validation.is_valid:
                errors_str = "; ".join(
                    f"[{e.code}] {e.message}" for e in validation.errors
                )
                raise ValueError(
                    f"Валидация агента '{agent_type}' не пройдена: {errors_str}"
                )
            logger.debug("Валидация агента '%s' пройдена", agent_type)

        # Разрешение зависимостей: явные > defaults > None
        resolved_llm = llm_adapter if llm_adapter is not None else self._default_llm_adapter
        resolved_pm = prompt_manager if prompt_manager is not None else self._default_prompt_manager

        return agent_class(config, resolved_llm, resolved_pm)

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