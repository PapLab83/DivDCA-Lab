"""
Фабрика приложения — сборка DI-контейнера и регистрация агентов.

Отделена от run.py чтобы:
- изолировать логику сборки от логики запуска
- переиспользовать в тестах и будущем API-слое
- явно документировать какие агенты регистрируются

Использование:
    container = build_app_container()
    agent = container.factory.create_agent("event_generation", container.config)
"""
import logging

from agents.config import build_container
from agents.core.container import Container
from agents.tasks.event_generation.agent import EventGenerationAgent

logger = logging.getLogger(__name__)

# Реестр агентов приложения.
# Ключ — строковый идентификатор задачи, значение — класс агента.
# Добавляй новые агенты сюда при расширении системы.
_AGENT_REGISTRY = {
    "event_generation": EventGenerationAgent,
}


def build_app_container() -> Container:
    """
    Собирает DI-контейнер и регистрирует все агенты приложения.

    Единственная точка где определяется состав агентов.
    run.py, тесты и будущий API-слой используют эту функцию
    вместо ручной сборки.

    Returns:
        Готовый Container со всеми зарегистрированными агентами.
    """
    container = build_container()

    for agent_type, agent_class in _AGENT_REGISTRY.items():
        container.factory.register(agent_type, agent_class)

    logger.info(
        "Контейнер собран: provider=%s, model=%s, агенты=%s",
        container.config.llm_config.provider,
        container.config.llm_config.model,
        container.factory.list_agents(),
    )

    return container