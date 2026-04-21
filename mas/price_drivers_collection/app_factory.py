# mas/price_drivers_collection/app_factory.py
"""
Фабрика приложения — сборка DI-контейнера и регистрация агентов.

Отделена от run.py чтобы:
- изолировать логику сборки от логики запуска
- переиспользовать в тестах и будущем API-слое
- явно документировать какие агенты регистрируются

Добавление нового LLM-провайдера:
    from agents.core.llm.engines.base_engine import BaseLLMEngine
    from agents.core.base_agent import LLMProvider

    class MyEngine(BaseLLMEngine):
        ...

    container = build_app_container(
        engine_registry={LLMProvider.CUSTOM: MyEngine}
    )

Использование:
    container = build_app_container()
    agent = build_event_generation_agent(container)
"""
import logging
from typing import Dict, Optional, Type

from agents.core.base_agent import LLMProvider
from agents.core.base_agent import BaseAgent
from agents.core.container import Container
from agents.core.llm.engines.base_engine import BaseLLMEngine
from agents.config import build_container
from agents.tasks.event_generation.agent import EventGenerationAgent

logger = logging.getLogger(__name__)

# Реестр агентов приложения.
# Ключ — строковый идентификатор задачи, значение — класс агента.
# Добавляй новые агенты сюда при расширении системы.
_AGENT_REGISTRY = {
    "event_generation": EventGenerationAgent,
}


def build_app_container(
    engine_registry: Optional[Dict[LLMProvider, Type[BaseLLMEngine]]] = None,
) -> Container:
    """
    Собирает DI-контейнер и регистрирует все агенты приложения.

    Единственная точка где определяется состав агентов.
    run.py, тесты и будущий API-слой используют эту функцию
    вместо ручной сборки.

    Args:
        engine_registry: реестр LLM-движков для контейнера.
            Используйте для добавления кастомных провайдеров.
            None → используются дефолтные провайдеры.

            Пример:
                container = build_app_container(
                    engine_registry={LLMProvider.CUSTOM: MyEngine}
                )

    Returns:
        Готовый Container со всеми зарегистрированными агентами.
    """
    container = build_container(engine_registry=engine_registry)

    for agent_type, agent_class in _AGENT_REGISTRY.items():
        container.factory.register(agent_type, agent_class)

    logger.info(
        "Контейнер собран: provider=%s, model=%s, агенты=%s",
        container.config.llm_config.provider,
        container.config.llm_config.model,
        container.factory.list_agents(),
    )

    return container


def build_event_generation_agent(container: Container) -> BaseAgent:
    """
    Создаёт готового EventGenerationAgent из контейнера.

    Единственная точка где знание об "event_generation" как строке
    живёт в app_factory — это конфигурация приложения, не pipeline-логика.

    Агент получает llm_adapter и prompt_manager автоматически
    через default-зависимости Container'а.

    Args:
        container: собранный DI-контейнер (из build_app_container())

    Returns:
        Готовый к использованию EventGenerationAgent.

    Использование:
        container = build_app_container()
        agent = build_event_generation_agent(container)
        run_collection(agent, tickers_data)
    """
    agent = container.factory.create_agent(
        agent_type="event_generation",
        config=container.config,
    )
    logger.info(
        "Создан агент: %s (provider=%s, model=%s)",
        agent.__class__.__name__,
        container.config.llm_config.provider,
        container.config.llm_config.model,
    )
    return agent