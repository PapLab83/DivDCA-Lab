"""
DI-контейнер — единая точка сборки всех зависимостей.

Контейнер владеет lifecycle компонентов и предоставляет
их через свойства. Не является singleton — можно создавать
несколько экземпляров (тесты, multi-tenant, A/B).
"""
import logging
from typing import Optional

from agents.core.base_agent import AgentConfig, CacheProtocol
from agents.core.agent_registry import AgentRegistry
from agents.core.agent_validator import AgentValidator
from agents.core.agent_factory import AgentFactory
from agents.core.llm.adapter import LLMAdapter
from agents.core.skills.cache import InMemoryCache


logger = logging.getLogger(__name__)


class Container:
    """
    Корневой DI-контейнер приложения.

    Собирает и связывает компоненты:
        registry → validator → factory
        config → cache → llm_adapter

    Использование:
        container = Container(config)
        agent = container.factory.create_agent("event_gen", config)

    Тесты:
        container = Container(mock_config)  # изолированный экземпляр
    """

    def __init__(
        self,
        config: AgentConfig,
        *,
        registry: Optional[AgentRegistry] = None,
        cache: Optional[CacheProtocol] = None,
    ) -> None:
        """
        Args:
            config: конфигурация агента (LLM + API + режим)
            registry: реестр метаданных (если None — создаётся с дефолтами)
            cache: кэш для LLM-ответов (если None — создаётся InMemoryCache
                   при config.cache_enabled, иначе без кэша)
        """
        self._config = config

        # ── Registry → Validator ──
        self._registry = registry or AgentRegistry()
        self._validator = AgentValidator(self._registry)

        # ── Factory ──
        self._factory = AgentFactory(
            registry=self._registry,
            validator=self._validator,
        )

        # ── Cache ──
        if cache is not None:
            self._cache: Optional[CacheProtocol] = cache
        elif config.cache_enabled:
            self._cache = InMemoryCache()
        else:
            self._cache = None

        # ── LLM Adapter ──
        self._llm_adapter = LLMAdapter(
            config=config.llm_config,
            api_config=config.api_config,
            cache=self._cache,
        )

        logger.info(
            "Container создан: provider=%s, model=%s, cache=%s, agents=%d",
            config.llm_config.provider,
            config.llm_config.model,
            type(self._cache).__name__ if self._cache else "disabled",
            len(self._registry.list_agents()),
        )

    # ── Свойства (read-only) ──

    @property
    def config(self) -> AgentConfig:
        return self._config

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    @property
    def validator(self) -> AgentValidator:
        return self._validator

    @property
    def factory(self) -> AgentFactory:
        return self._factory

    @property
    def llm_adapter(self) -> LLMAdapter:
        return self._llm_adapter

    @property
    def cache(self) -> Optional[CacheProtocol]:
        return self._cache

    def __repr__(self) -> str:
        return (
            f"Container("
            f"provider={self._config.llm_config.provider!r}, "
            f"agents={self._factory.list_agents()!r})"
        )
