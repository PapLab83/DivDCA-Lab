"""
DI-контейнер — единая точка сборки всех зависимостей.

Контейнер владеет lifecycle компонентов и предоставляет
их через свойства. Не является singleton — можно создавать
несколько экземпляров (тесты, multi-tenant, A/B).
"""

__all__ = [
    "Container",
]

import logging
from pathlib import Path
from typing import Dict, Optional, Type, cast

from agents.core.base_agent import (
    AgentConfig,
    CacheProtocol,
    LLMAdapterProtocol,
    LLMProvider,
    PromptManagerProtocol,
)
from agents.core.agent_registry import AgentRegistry
from agents.core.agent_validator import AgentValidator
from agents.core.agent_factory import AgentFactory
from agents.core.llm.adapter import LLMAdapter
from agents.core.llm.engines.base_engine import BaseLLMEngine
from agents.core.skills.cache import InMemoryCache
from agents.core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

# Дефолтный путь к промптам относительно пакета agents.
# Используется если AgentConfig.prompts_path не задан.
_DEFAULT_PROMPTS_PATH = Path(__file__).parent.parent / "prompts"


class Container:
    """
    Корневой DI-контейнер приложения.

    Собирает и связывает компоненты:
        config → cache → llm_adapter → prompt_manager
        registry → validator → factory(с defaults)

    Добавление кастомного LLM-провайдера:
        Передайте engine_registry с нужным провайдером.
        Каждый Container полностью изолирован — разные экземпляры
        могут использовать разные провайдеры без конфликтов.

        Пример:
            from agents.core.llm.engines.base_engine import BaseLLMEngine

            class MyCustomEngine(BaseLLMEngine):
                ...

            engine_registry = {LLMProvider.CUSTOM: MyCustomEngine}
            container = Container(config, engine_registry=engine_registry)

    Путь к промптам:
        Приоритет: config.prompts_path → дефолтный путь (agents/prompts/).
        Передайте AgentConfig(prompts_path="...") для переопределения.

    Использование:
        container = Container(config)
        agent = container.factory.create_agent("event_gen", config)
        # agent уже имеет llm_adapter и prompt_manager

    Тесты:
        config = AgentConfig(prompts_path="/tmp/test_prompts")
        container = Container(config)  # изолированный экземпляр
    """

    def __init__(
            self,
            config: AgentConfig,
            *,
            registry: Optional[AgentRegistry] = None,
            cache: Optional[CacheProtocol] = None,
            engine_registry: Optional[Dict[LLMProvider, Type[BaseLLMEngine]]] = None,
    ) -> None:
        """
        Args:
            config: конфигурация агента (провайдер, модель, кэш, промпты)
            registry: опциональный AgentRegistry (для тестов или кастомной сборки)
            cache: опциональный кэш (реализует CacheProtocol)
            engine_registry: реестр LLM-движков для этого контейнера.
                Рекомендуемый способ добавления кастомных провайдеров.
                Каждый Container изолирован — разные контейнеры могут
                использовать разные наборы провайдеров.

                None → используются дефолтные провайдеры
                    (OpenAI, Claude, Gemini, Mock).

                Пример добавления провайдера:
                    engine_registry = {LLMProvider.CUSTOM: MyEngine}
                    container = Container(config, engine_registry=engine_registry)

                Пример полного переопределения (для тестов):
                    engine_registry = {LLMProvider.MOCK: MyTestEngine}
                    container = Container(config, engine_registry=engine_registry)
        """
        self._config = config

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
            engine_registry=engine_registry,
        )

        # ── PromptManager ──
        # Приоритет пути: config.prompts_path → дефолтный путь пакета
        prompts_path = (
            Path(config.prompts_path)
            if config.prompts_path is not None
            else _DEFAULT_PROMPTS_PATH
        )

        if prompts_path.is_dir():
            self._prompt_manager: PromptManager = PromptManager.from_yaml(str(prompts_path))
        else:
            logger.warning(
                "Директория промптов не найдена: %s. "
                "PromptManager создан пустым — агенты упадут при вызове get_prompt(). "
                "Зарегистрируйте промпты вручную через prompt_manager.register() "
                "или передайте корректный путь через AgentConfig(prompts_path=...).",
                prompts_path,
            )
            self._prompt_manager = PromptManager()

        # ── Registry → Validator → Factory (с defaults) ──
        self._registry = registry or AgentRegistry()
        self._validator = AgentValidator(self._registry)
        self._factory = AgentFactory(
            registry=self._registry,
            validator=self._validator,
            default_llm_adapter=cast(LLMAdapterProtocol, self._llm_adapter),
            default_prompt_manager=cast(PromptManagerProtocol, self._prompt_manager),
        )

        logger.info(
            "Container создан: provider=%s, model=%s, cache=%s, "
            "prompts_path=%s, agents_total=%d, agents_bound=%d, "
            "custom_engines=%s",
            config.llm_config.provider,
            config.llm_config.model,
            type(self._cache).__name__ if self._cache else "disabled",
            prompts_path,
            len(self._registry.list_agents()),
            len(self._registry.list_bound_agents()),
            list(engine_registry.keys()) if engine_registry else "defaults",
        )

    # ── Свойства (read-only) ──
    @property
    def prompt_manager(self) -> PromptManager:
        return self._prompt_manager

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