"""
Фикстуры для тестов mas pipeline-слоя.
"""
import pytest

from agents.core.base_agent import (
    AgentConfig,
    AgentContext,
    AgentResult,
    BaseAgent,
    LLMConfig,
    LLMProvider,
)
from agents.core.container import Container
from agents.tasks.event_generation.agent import EventGenerationAgent
from mas.price_drivers_collection.mock_data import MOCK_TICKERS


# ── Тестовые агенты ───────────────────────────────────────────────

class AlwaysSuccessAgent(BaseAgent):
    """Агент, который всегда возвращает успех с фиксированными данными."""

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "reason_short": "Test reason",
                "reason_long": "This is a test reason for testing",
                "confidence": 0.95,
            },
            prompt_version="test-1.0",
        )


class AlwaysFailAgent(BaseAgent):
    """Агент, который всегда падает с исключением."""

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        raise RuntimeError("Simulated LLM failure")


class PartialFailAgent(BaseAgent):
    """
    Агент, который падает на чётных годах.
    Позволяет тестировать смешанные результаты.
    """

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        year = context.metadata.get("year", 0)
        if year % 2 == 0:
            raise RuntimeError(f"Simulated failure for year {year}")
        return AgentResult(
            success=True,
            data={
                "reason_short": f"Reason for {year}",
                "reason_long": f"Detailed reason for year {year}",
                "confidence": 0.8,
            },
        )


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