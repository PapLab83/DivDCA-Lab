"""
Общие фикстуры для тестов agents.
"""
import pytest

from agents.core.base_agent import AgentConfig, AgentContext, LLMConfig, LLMProvider
from agents.core.agent_factory import AgentFactory
from agents.core.container import Container


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
def context() -> AgentContext:
    """Тестовый контекст."""
    return AgentContext(agent_id="test-001", task="test_task")