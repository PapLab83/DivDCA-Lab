"""
Фикстуры для тестов mas pipeline-слоя.

Тестовые агенты импортируются из agents.tests.shared_agents —
единственного источника правды. Дублирования нет.
"""
import pytest

from agents.core.base_agent import AgentConfig, LLMConfig, LLMProvider
from agents.core.container import Container
from agents.tasks.event_generation.agent import EventGenerationAgent
from agents.tests.shared_agents import (
    AlwaysFailAgent,
    AlwaysSuccessAgent,
    PartialFailAgent,
)
from mas.price_drivers_collection.mock_data import MOCK_TICKERS


# ── Конфигурации ──────────────────────────────────────────────────

@pytest.fixture
def mock_config() -> AgentConfig:
    """Конфигурация с mock-провайдером."""
    return AgentConfig(
        llm_config=LLMConfig(provider=LLMProvider.MOCK),
        cache_enabled=False,
    )


# ── Контейнеры ────────────────────────────────────────────────────

@pytest.fixture
def container_with_success_agent(mock_config) -> Container:
    """Контейнер с агентом, который всегда успешен."""
    container = Container(mock_config)
    container.factory.register("event_generation", AlwaysSuccessAgent)
    return container


@pytest.fixture
def container_with_fail_agent(mock_config) -> Container:
    """Контейнер с агентом, который всегда падает."""
    container = Container(mock_config)
    container.factory.register("event_generation", AlwaysFailAgent)
    return container


@pytest.fixture
def container_with_partial_fail_agent(mock_config) -> Container:
    """Контейнер с агентом, который падает на чётных годах."""
    container = Container(mock_config)
    container.factory.register("event_generation", PartialFailAgent)
    return container


@pytest.fixture
def integration_container(mock_config) -> Container:
    """
    Полный integration-контейнер:
    реальный EventGenerationAgent + MockEngine + PromptManager.
    Factory автоматически инжектит llm_adapter и prompt_manager.
    """
    container = Container(mock_config)
    container.factory.register("event_generation", EventGenerationAgent)
    return container


# ── Данные ────────────────────────────────────────────────────────

@pytest.fixture
def single_ticker_data():
    """Один тикер с 2 записями — минимальный набор."""
    return {
        "ticker": "TEST",
        "records": [
            {"year": 2021, "price": 100.0, "dividend": 2.0, "yoy_change": 5.0},
            {"year": 2022, "price": 110.0, "dividend": 2.1, "yoy_change": 5.0},
        ],
    }


@pytest.fixture
def single_record():
    """Одна запись."""
    return {"year": 2021, "price": 100.0, "dividend": 2.0, "yoy_change": 5.0}


@pytest.fixture
def empty_records_ticker():
    """Тикер без записей."""
    return {"ticker": "EMPTY", "records": []}


@pytest.fixture
def mock_tickers_data():
    """Полный набор mock-данных."""
    return MOCK_TICKERS