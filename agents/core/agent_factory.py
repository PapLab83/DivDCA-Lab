"""
Фабрика для создания агентов.
Опционально связана с AgentRegistry и AgentValidator для проверки совместимости.
"""
import logging
import threading
from typing import Dict, List, Optional, Type

from agents.core.base_agent import AgentConfig, BaseAgent, LLMAdapterProtocol


logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Фабрика для создания агентов (потокобезопасная, singleton).

    Если передан registry + validator — при создании агента
    автоматически проверяется совместимость с конфигурацией.
    """

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
        if hasattr(self, "_agents"):
            return
        self._agents: Dict[str, Type[BaseAgent]] = {}
        self._lock = threading.Lock()
        # Опциональные зависимости — устанавливаются через set_registry
        self._registry: Optional["AgentRegistry"] = None
        self._validator: Optional["AgentValidator"] = None

    @classmethod
    def _reset(cls) -> None:
        """Сбрасывает singleton. Только для тестов."""
        with cls._init_lock:
            cls._instance = None

    # ── связь с registry / validator ──────────────────────────────

    def set_registry(
        self,
        registry: "AgentRegistry",
        validator: Optional["AgentValidator"] = None,
    ) -> None:
        """
        Подключает реестр метаданных и (опционально) валидатор.

        Если validator не передан, но registry передан —
        создаётся валидатор автоматически.

        Args:
            registry: реестр метаданных агентов
            validator: валидатор совместимости (опционально)
        """
        from agents.core.agent_registry import AgentRegistry
        from agents.core.agent_validator import AgentValidator

        self._registry = registry
        self._validator = validator or AgentValidator(registry)
        logger.info(
            "Factory связана с registry (%d агентов)",
            len(registry.list_agents()),
        )

    # ── регистрация ───────────────────────────────────────────────

    def register(self, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Регистрирует новый тип агента.

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
                    agent_type, existing, agent_class.__name__,
                )
            self._agents[agent_type] = agent_class
            logger.debug("Зарегистрирован тип агента: %s -> %s", agent_type, agent_class.__name__)

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

        Если подключён registry+validator — проверяет совместимость
        агента с конфигурацией перед созданием.

        Args:
            agent_type: строковый идентификатор
            config: конфигурация агента
            llm_adapter: LLM адаптер (опционально)
            skip_validation: пропустить валидацию (для тестов)

        Raises:
            ValueError: тип агента не зарегистрирован
            ValueError: валидация не пройдена (provider unsupported и т.д.)
        """
        with self._lock:
            if agent_type not in self._agents:
                raise ValueError(
                    f"Неизвестный тип агента: {agent_type}. "
                    f"Доступные: {list(self._agents.keys())}"
                )
            agent_class = self._agents[agent_type]

        # Валидация через registry (если подключён)
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
        """
        Возвращает описание агента из registry (если подключён).
        """
        if self._registry is None:
            return None
        return self._registry.format_info(agent_type)


# Глобальный экземпляр
default_factory = AgentFactory()
register_agent = default_factory.register_agent