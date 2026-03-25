"""
Минимальные тесты для core-компонентов.
Запуск: pytest agents/tests/test_core.py -v
"""
import json
import pytest

from agents.core.base_agent import (
    AgentConfig,
    AgentContext,
    AgentResult,
    BaseAgent,
    LLMConfig,
    LLMParseError,
    LLMProvider,
    ApiConfig,
)
from agents.core.agent_factory import AgentFactory
from agents.core.agent_registry import AgentRegistry, AgentMetadata
from agents.core.llm.adapter import LLMAdapter
from agents.core.skills.cache import InMemoryCache


# ─────────────────────────── Fixtures ─────────────────────────────

class MockAgent(BaseAgent):
    """Тестовый агент для проверки BaseAgent."""

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            success=True,
            data={"message": "ok"},
        )


class FailingAgent(BaseAgent):
    """Агент, который всегда падает."""

    def _execute_internal(self, context: AgentContext) -> AgentResult:
        raise ValueError("Тестовая ошибка")


@pytest.fixture
def mock_config() -> AgentConfig:
    return AgentConfig(
        llm_config=LLMConfig(provider=LLMProvider.MOCK),
    )


@pytest.fixture
def context() -> AgentContext:
    return AgentContext(agent_id="test-001", task="test_task")


# ─────────────────────────── BaseAgent ────────────────────────────

class TestBaseAgent:
    def test_execute_success(self, mock_config, context):
        agent = MockAgent(mock_config)
        result = agent.execute(context)

        assert result.success is True
        assert result.data == {"message": "ok"}
        assert result.duration_ms is not None
        assert result.duration_ms >= 0
        assert result.metadata["agent_class"] == "MockAgent"

    def test_execute_error_handling(self, mock_config, context):
        agent = FailingAgent(mock_config)
        result = agent.execute(context)

        assert result.success is False
        assert "ValueError" in result.error
        assert "Тестовая ошибка" in result.error

    def test_repr(self, mock_config):
        agent = MockAgent(mock_config)
        assert "MockAgent" in repr(agent)

    def test_parse_response_valid_json(self, mock_config):
        agent = MockAgent(mock_config)
        data = agent._parse_response('{"key": "value"}')
        assert data == {"key": "value"}

    def test_parse_response_markdown_block(self, mock_config):
        agent = MockAgent(mock_config)
        response = '```json\n{"key": "value"}\n```'
        data = agent._parse_response(response)
        assert data == {"key": "value"}

    def test_parse_response_invalid_json(self, mock_config):
        agent = MockAgent(mock_config)
        with pytest.raises(LLMParseError) as exc_info:
            agent._parse_response("not json at all")
        assert exc_info.value.raw_response == "not json at all"

    def test_call_llm_without_adapter_raises(self, mock_config):
        agent = MockAgent(mock_config)
        with pytest.raises(RuntimeError, match="llm_adapter не инициализирован"):
            agent._call_llm("test prompt")


# ─────────────────────────── AgentFactory ─────────────────────────

class TestAgentFactory:
    def test_register_and_create(self, mock_config):
        factory = AgentFactory()
        factory.register("mock", MockAgent)

        agent = factory.create_agent("mock", mock_config)
        assert isinstance(agent, MockAgent)

    def test_create_unknown_raises(self, mock_config):
        factory = AgentFactory()
        with pytest.raises(ValueError, match="Неизвестный тип агента"):
            factory.create_agent("nonexistent", mock_config)

    def test_register_non_agent_raises(self):
        factory = AgentFactory()
        with pytest.raises(TypeError, match="должен быть наследником BaseAgent"):
            factory.register("bad", dict)  # type: ignore

    def test_list_agents(self):
        factory = AgentFactory()
        factory.register("mock", MockAgent)
        assert "mock" in factory.list_agents()

    def test_unregister(self):
        factory = AgentFactory()
        factory.register("mock", MockAgent)
        factory.unregister("mock")
        assert "mock" not in factory.list_agents()

    def test_decorator_registration(self, mock_config):
        factory = AgentFactory()

        @factory.register_agent("decorated")
        class DecoratedAgent(BaseAgent):
            def _execute_internal(self, context):
                return AgentResult(success=True)

        assert "decorated" in factory.list_agents()
        agent = factory.create_agent("decorated", mock_config)
        assert isinstance(agent, DecoratedAgent)


# ─────────────────────────── AgentRegistry ────────────────────────

class TestAgentRegistry:
    def test_defaults_loaded(self):
        registry = AgentRegistry()
        assert "event_generation" in registry.list_agents()
        assert "event_validation" in registry.list_agents()

    def test_no_defaults(self):
        registry = AgentRegistry(load_defaults=False)
        assert registry.list_agents() == []

    def test_get_existing(self):
        registry = AgentRegistry()
        meta = registry.get("event_generation")
        assert meta is not None
        assert meta.name == "Event Generation Agent"

    def test_get_nonexistent(self):
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None

    def test_format_info(self):
        registry = AgentRegistry()
        info = registry.format_info("event_generation")
        assert "Event Generation Agent" in info

    def test_format_info_not_found(self):
        registry = AgentRegistry()
        info = registry.format_info("nonexistent")
        assert "не найден" in info

    def test_register_custom(self):
        registry = AgentRegistry(load_defaults=False)
        registry.register("custom", AgentMetadata(
            name="Custom", description="test", version="0.1",
            inputs=["a"], outputs=["b"],
        ))
        assert registry.get("custom") is not None


# ─────────────────────────── LLMAdapter ───────────────────────────

class TestLLMAdapter:
    def test_mock_call(self):
        config = LLMConfig(provider=LLMProvider.MOCK)
        adapter = LLMAdapter(config)

        response = adapter.call("test prompt")
        data = json.loads(response)

        assert "reason_short" in data
        assert data["confidence"] == 1.0

    def test_mock_with_cache(self):
        config = LLMConfig(provider=LLMProvider.MOCK)
        cache = InMemoryCache()
        adapter = LLMAdapter(config, cache=cache)

        # Первый вызов — cache miss
        response1 = adapter.call("test prompt")
        assert cache.size() == 0  # mock не сохраняет в кэш (mock обходит кэш)

    def test_tokens_tracking(self):
        config = LLMConfig(provider=LLMProvider.MOCK)
        adapter = LLMAdapter(config)

        assert adapter.get_tokens_used() == 0
        adapter.call("test")
        # Mock не добавляет токены
        assert adapter.get_tokens_used() == 0

        adapter.reset_tokens()
        assert adapter.get_tokens_used() == 0


# ─────────────────────────── InMemoryCache ────────────────────────

class TestInMemoryCache:
    def test_set_and_get(self):
        cache = InMemoryCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_miss(self):
        cache = InMemoryCache()
        assert cache.get("nonexistent") is None

    def test_max_size_eviction(self):
        cache = InMemoryCache(max_size=2)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")  # должен вытеснить k1
        assert cache.size() == 2

    def test_clear(self):
        cache = InMemoryCache()
        cache.set("k1", "v1")
        cache.clear()
        assert cache.size() == 0
        assert cache.get("k1") is None


# ─────────────────────────── Configs ──────────────────────────────

class TestConfigs:
    def test_llm_config_defaults(self):
        config = LLMConfig()
        assert config.provider == LLMProvider.OPENAI
        assert config.temperature == 0.7

    def test_llm_config_invalid_temperature(self):
        with pytest.raises(ValueError, match="temperature"):
            LLMConfig(temperature=3.0)

    def test_llm_config_invalid_tokens(self):
        with pytest.raises(ValueError, match="max_tokens"):
            LLMConfig(max_tokens=-1)

    def test_api_config_repr_masks_key(self):
        config = ApiConfig(api_key="sk-1234567890abcdef")
        repr_str = repr(config)
        assert "sk-1****" in repr_str
        assert "1234567890abcdef" not in repr_str

    def test_api_config_repr_short_key(self):
        config = ApiConfig(api_key="abc")
        repr_str = repr(config)
        assert "****" in repr_str

    def test_agent_result_is_frozen(self):
        result = AgentResult(success=True)
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore