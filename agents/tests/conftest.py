"""
Общие фикстуры для тестов agents.
"""
import pytest

from agents.core.agent_factory import AgentFactory


@pytest.fixture(autouse=True)
def reset_agent_factory():
    """Сбрасывает singleton AgentFactory после каждого теста."""
    yield
    AgentFactory._reset()