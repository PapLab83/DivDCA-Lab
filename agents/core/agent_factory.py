"""
Фабрика для создания агентов.
Принимает registry и validator через конструктор (DI).
Не является singleton — lifecycle управляется Container'ом.
"""
import logging
import threading
from typing import Dict, List, Optional, Type

from agents.core.base_agent import AgentConfig, BaseAgent, LLMAdapterProtocol


logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Фабрика для создания агентов (потокобезопасная).

    Получает registry и validator через конструктор.
    При создании агента автоматически проверяет совместимость
    с конфигурацией (если validator передан).
    """

    def __init__(
        self,
        registry: Optional["AgentRegistry"] = None,
        validator: Optional["AgentValidator"] = None,
    ) -> None:
        """
        Args:
            registry: реестр метаданных агентов (опционально)
            validator: валидатор совместимости (опционально;
                       если registry передан без validator —
                       validator создаётся автоматически)
        """
        self._agents: Dict[str, Type[BaseAgent]] = {}
        self._lock = threading.Lock()
        self._registry = registry
        self._validator = validator

        # Автосоздание validator если передан только registry
        if self._registry is not None and self._validator is None:
            from agents.core.agent_validator import AgentValidator
            self._validator = AgentValidator(self._registry)

        if self._registry is not None:
            logger.info(
                "Factory создана с registry (%d агентов)",
                len(self._registry.list_agents()),
            )
        else:
            logger.debug("Factory создана без registry")

    # ── регистрация ───────────────────────────────────────────────

    def register(self, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Регистрирует новый тип агента.

        Raises:
            TypeError: если agent_class не наследник BaseAgent
        """
        if not issubclass(agent_class, BaseAgent):
            raise TypeError(
                f"{agent_class.__name__} должен быть наследником BaseAgent"
            )

        with self._lock:
            if agent_type in self._agents:
                existing = self._agents[agent_type].__name__
                logger.warning(
                    "Тип '%s' уже зарегистрирован (%s), перезаписывается на %s",
                    agent_type, existing, agent_class.__name__,
                )
            self._agents[agent_type] = agent_class
            logger.debug(
                "Зарегистрирован: %s -> %s",
                agent_type, agent_class.__name__,
            )

    def register_agent(self, agent_type: str):
        """Декоратор для автоматической регистрации агента."""
        def decorator(cls: Type[BaseAgent]) -> Type[BaseAgent]:
            self.register(agent_type, cls)
            return cls
        return decorator

    def unregister(self, agent_type: str) -> None:
        """Удаляет агента из реестра."""
        with self._lock:
            self._agents.pop(agent_type, None)

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

        Если подключён validator — проверяет совместимость
        агента с конфигурацией перед созданием.

        Args:
            agent_type: строковый идентификатор
            config: конфигурация агента
            llm_adapter: LLM адаптер (опционально)
            skip_validation: пропустить валидацию

        Raises:
            ValueError: тип не зарегистрирован или валидация не пройдена
        """
        with self._lock:
            if agent_type not in self._agents:
                raise ValueError(
                    f"Неизвестный тип агента: {agent_type}. "
                    f"Доступные: {list(self._agents.keys())}"
                )
            agent_class = self._agents[agent_type]

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
        """Список зарегистрированных типов агентов."""
        with self._lock:
            return list(self._agents.keys())

    def get_agent_info(self, agent_type: str) -> Optional[str]:
        """Описание агента из registry (если подключён)."""
        if self._registry is None:
            return None
        return self._registry.format_info(agent_type)