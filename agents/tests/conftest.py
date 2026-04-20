"""
Общие фикстуры для тестов agents.
"""
import pytest
import pytest_asyncio

from agents.core.base_agent import (
    AgentConfig,
    AgentContext,
    LLMConfig,
    LLMProvider,
)
from agents.core.agent_factory import AgentFactory
from agents.core.agent_registry import AgentRegistry
from agents.core.container import Container

from agents.tests.shared_agents import AlwaysSuccessAgent, AlwaysFailAgent

MockAgent = AlwaysSuccessAgent
FailingAgent = AlwaysFailAgent


# ── Sync фикстуры ────────────────────────────────────────────────

@pytest.fixture
def mock_config() -> AgentConfig:
    """Конфигурация с mock-провайдером."""
    return AgentConfig(
        llm_config=LLMConfig(provider=LLMProvider.MOCK),
    )


@pytest.fixture
def container(mock_config) -> Container:
    """Изолированный DI-контейнер для тестов."""
    return Container(mock_config)


@pytest.fixture
def factory(container) -> AgentFactory:
    """Фабрика из контейнера."""
    return container.factory


@pytest.fixture
def registry(container) -> AgentRegistry:
    """Registry из контейнера."""
    return container.registry


@pytest.fixture
def context() -> AgentContext:
    """Тестовый контекст."""
    return AgentContext(agent_id="test-001", task="test_task")


# ── Async фикстуры ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def async_context() -> AgentContext:
    """Тестовый контекст для async тестов."""
    return AgentContext(agent_id="async-001", task="async_test")