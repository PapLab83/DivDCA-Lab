"""
Тесты для core-компонентов.
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
    LLMProvider,
    ApiConfig,
)
from agents.core.llm.exceptions import LLMParseError, LLMEngineError
from agents.core.agent_registry import AgentRegistry, AgentMetadata
from agents.core.llm.adapter import LLMAdapter
from agents.core.llm.engines.claude_engine import ClaudeEngine
from agents.core.llm.engines.gemini_engine import GeminiEngine
from agents.core.skills.cache import InMemoryCache
from agents.core.agent_factory import AgentFactory

from agents.tests.conftest import MockAgent, FailingAgent


# ─────────────────────────── Fixtures ─────────────────────────────

@pytest.fixture
def mock_config() -> AgentConfig:
    return AgentConfig(
        llm_config=LLMConfig(provider=LLMProvider.MOCK),
    )


@pytest.fixture
def context() -> AgentContext:
    return AgentContext(agent_id="test-001", task="test_task")


# ─────────────────────────── BaseAgent (sync) ─────────────────────

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


# ─────────────────────────── BaseAgent (async) ────────────────────

class TestBaseAgentAsync:
    @pytest.mark.asyncio
    async def test_execute_async_success(self, mock_config):
        context = AgentContext(agent_id="async-001", task="async_test")
        agent = MockAgent(mock_config)
        result = await agent.execute_async(context)

        assert result.success is True
        assert result.data == {"message": "ok"}
        assert result.duration_ms is not None
        assert result.duration_ms >= 0
        assert result.metadata["agent_class"] == "MockAgent"

    @pytest.mark.asyncio
    async def test_execute_async_error_handling(self, mock_config):
        context = AgentContext(agent_id="async-002", task="async_fail")
        agent = FailingAgent(mock_config)
        result = await agent.execute_async(context)

        assert result.success is False
        assert "ValueError" in result.error
        assert "Тестовая ошибка" in result.error

    @pytest.mark.asyncio
    async def test_execute_async_runs_in_thread(self, mock_config):
        """Проверяем что sync _execute_internal не блокирует event loop."""
        import asyncio
        import threading

        captured_thread = {}

        class ThreadCapturingAgent(BaseAgent):
            def _execute_internal(self, context):
                captured_thread["name"] = threading.current_thread().name
                return AgentResult(success=True, data={"thread": captured_thread["name"]})

        context = AgentContext(agent_id="async-003", task="thread_test")
        agent = ThreadCapturingAgent(mock_config)
        result = await agent.execute_async(context)

        assert result.success is True
        # Должен выполняться НЕ в main thread (asyncio.to_thread)
        main_thread = threading.main_thread().name
        assert captured_thread["name"] != main_thread, (
            f"_execute_internal должен выполняться в отдельном потоке, "
            f"но выполнился в {captured_thread['name']}"
        )

    @pytest.mark.asyncio
    async def test_call_llm_async_without_adapter_raises(self, mock_config):
        agent = MockAgent(mock_config)
        with pytest.raises(RuntimeError, match="llm_adapter не инициализирован"):
            await agent._call_llm_async("test prompt")

    @pytest.mark.asyncio
    async def test_execute_async_with_custom_override(self, mock_config):
        """Агент с настоящей async реализацией."""

        class TrueAsyncAgent(BaseAgent):
            def _execute_internal(self, context):
                return AgentResult(success=False, error="sync fallback")

            async def _execute_internal_async(self, context):
                # Настоящая async логика
                return AgentResult(success=True, data={"async": True})

        context = AgentContext(agent_id="async-004", task="true_async")
        agent = TrueAsyncAgent(mock_config)
        result = await agent.execute_async(context)

        assert result.success is True
        assert result.data["async"] is True


# ─────────────────────────── LLMAdapter (async) ──────────────────

class TestLLMAdapterAsync:
    @pytest.mark.asyncio
    async def test_mock_acall(self):
        config = LLMConfig(provider=LLMProvider.MOCK)
        adapter = LLMAdapter(config)

        response = await adapter.acall("test prompt")
        data = json.loads(response)

        assert "reason_short" in data
        assert data["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_mock_acall_with_cache(self):
        config = LLMConfig(provider=LLMProvider.MOCK)
        cache = InMemoryCache()
        adapter = LLMAdapter(config, cache=cache)

        response1 = await adapter.acall("test prompt")
        assert cache.size() == 1

        response2 = await adapter.acall("test prompt")
        assert response1 == response2
        assert cache.size() == 1


# ─────────────────────────── AgentFactory ─────────────────────────

class TestAgentFactory:
    def test_register_and_create(self, factory, mock_config):
        factory.register("mock", MockAgent)
        agent = factory.create_agent("mock", mock_config, skip_validation=True)
        assert isinstance(agent, MockAgent)

    def test_create_unknown_raises(self, factory, mock_config):
        with pytest.raises(ValueError, match="Неизвестный тип агента"):
            factory.create_agent("nonexistent", mock_config)

    def test_create_unbound_raises(self, factory, mock_config):
        """Агент есть в registry (метаданные), но класс не привязан."""
        with pytest.raises(ValueError, match="класс не привязан"):
            factory.create_agent("event_generation", mock_config)

    def test_register_non_agent_raises(self, factory):
        with pytest.raises(TypeError, match="должен быть наследником BaseAgent"):
            factory.register("bad", dict)  # type: ignore[arg-type]

    def test_list_agents_only_bound(self, factory):
        """list_agents возвращает только агентов с привязанным классом."""
        assert "event_generation" not in factory.list_agents()
        factory.register("mock", MockAgent)
        assert "mock" in factory.list_agents()

    def test_list_all_agents(self, factory):
        """list_all_agents включает агентов без класса."""
        assert "event_generation" in factory.list_all_agents()

    def test_unregister(self, factory):
        factory.register("mock", MockAgent)
        factory.unregister("mock")
        assert "mock" not in factory.list_agents()

    def test_decorator_registration(self, factory, mock_config):
        @factory.register_agent("decorated")
        class DecoratedAgent(BaseAgent):
            def _execute_internal(self, context):
                return AgentResult(success=True)

        assert "decorated" in factory.list_agents()
        agent = factory.create_agent("decorated", mock_config, skip_validation=True)
        assert isinstance(agent, DecoratedAgent)

    # ── Auto-inject через Container ──────────────────────────────

    def test_create_agent_injects_default_llm_adapter(self, container, mock_config):
        """Factory автоматически инжектит llm_adapter из Container."""
        container.factory.register("mock", MockAgent)
        agent = container.factory.create_agent("mock", mock_config, skip_validation=True)
        assert agent.llm_adapter is not None
        assert agent.llm_adapter is container.llm_adapter

    def test_create_agent_injects_default_prompt_manager(self, container, mock_config):
        """Factory автоматически инжектит prompt_manager из Container."""
        container.factory.register("mock", MockAgent)
        agent = container.factory.create_agent("mock", mock_config, skip_validation=True)
        assert agent.prompt_manager is not None
        assert agent.prompt_manager is container.prompt_manager

    def test_explicit_llm_adapter_overrides_default(self, container, mock_config):
        """Явно переданный llm_adapter имеет приоритет над default."""
        container.factory.register("mock", MockAgent)

        custom_adapter = LLMAdapter(
            config=LLMConfig(provider=LLMProvider.MOCK),
        )
        agent = container.factory.create_agent(
            "mock", mock_config,
            llm_adapter=custom_adapter,
            skip_validation=True,
        )
        assert agent.llm_adapter is custom_adapter
        assert agent.llm_adapter is not container.llm_adapter

    def test_explicit_prompt_manager_overrides_default(self, container, mock_config):
        """Явно переданный prompt_manager имеет приоритет над default."""
        from agents.core.prompt_manager import PromptManager

        container.factory.register("mock", MockAgent)

        custom_pm = PromptManager()
        agent = container.factory.create_agent(
            "mock", mock_config,
            prompt_manager=custom_pm,  # type: ignore[arg-type]
            skip_validation=True,
        )
        assert agent.prompt_manager is custom_pm
        assert agent.prompt_manager is not container.prompt_manager

    def test_factory_without_defaults_creates_agent_without_adapters(self):
        """Factory без defaults — агент создаётся с None адаптерами."""
        registry = AgentRegistry(load_defaults=False)
        factory = AgentFactory(registry=registry)
        factory.register("mock", MockAgent)

        config = AgentConfig(llm_config=LLMConfig(provider=LLMProvider.MOCK))
        agent = factory.create_agent("mock", config, skip_validation=True)

        assert agent.llm_adapter is None
        assert agent.prompt_manager is None


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
        assert meta.agent_class is None  # дефолты без класса

    def test_get_nonexistent(self):
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None

    def test_format_info(self):
        registry = AgentRegistry()
        info = registry.format_info("event_generation")
        assert "Event Generation Agent" in info
        assert "<не привязан>" in info

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
        assert registry.get("custom").agent_class is None

    def test_bind_class(self):
        registry = AgentRegistry(load_defaults=False)
        registry.register("test", AgentMetadata(
            name="Test", description="test", version="0.1",
            inputs=[], outputs=[],
        ))
        registry.bind_class("test", MockAgent)
        assert registry.get_class("test") is MockAgent

    def test_bind_class_auto_metadata(self):
        """bind_class без предварительного register — автоматические метаданные."""
        registry = AgentRegistry(load_defaults=False)
        registry.bind_class("auto", MockAgent)
        meta = registry.get("auto")
        assert meta is not None
        assert meta.agent_class is MockAgent
        assert meta.version == "0.0.0"  # auto-generated

    def test_bind_class_preserves_metadata(self):
        """bind_class сохраняет существующие метаданные."""
        registry = AgentRegistry(load_defaults=False)
        registry.register("rich", AgentMetadata(
            name="Rich Agent", description="detailed", version="1.0.0",
            inputs=["a", "b"], outputs=["c"],
        ))
        registry.bind_class("rich", MockAgent)
        meta = registry.get("rich")
        assert meta.name == "Rich Agent"
        assert meta.version == "1.0.0"
        assert meta.agent_class is MockAgent

    def test_list_bound_agents(self):
        registry = AgentRegistry(load_defaults=False)
        registry.register("meta_only", AgentMetadata(
            name="M", description="", version="0.1", inputs=[], outputs=[],
        ))
        registry.bind_class("with_class", MockAgent)
        assert "with_class" in registry.list_bound_agents()
        assert "meta_only" not in registry.list_bound_agents()

    def test_bind_non_agent_raises(self):
        registry = AgentRegistry(load_defaults=False)
        with pytest.raises(TypeError, match="должен быть наследником BaseAgent"):
            registry.bind_class("bad", dict)


# ─────────────────────────── Engine Validation ────────────────────

class TestEngineValidation:
    def test_claude_engine_requires_base_url(self):
        config = LLMConfig(provider=LLMProvider.CLAUDE, model="claude-3-opus")
        api_config = ApiConfig(api_key="test-key", base_url="")

        with pytest.raises(LLMEngineError, match="прокси"):
            ClaudeEngine(config, api_config)

    def test_gemini_engine_requires_base_url(self):
        config = LLMConfig(provider=LLMProvider.GEMINI, model="gemini-pro")
        api_config = ApiConfig(api_key="test-key", base_url="")

        with pytest.raises(LLMEngineError, match="прокси"):
            GeminiEngine(config, api_config)

    def test_claude_engine_accepts_base_url(self):
        """С base_url — не падает (openai пакет нужен)."""
        config = LLMConfig(provider=LLMProvider.CLAUDE, model="claude-3-opus")
        api_config = ApiConfig(api_key="test-key", base_url="http://localhost:4000/v1")

        try:
            engine = ClaudeEngine(config, api_config)
            assert engine is not None
        except LLMEngineError as e:
            if "openai" in str(e).lower():
                pytest.skip("openai пакет не установлен")
            raise

    def test_gemini_engine_accepts_base_url(self):
        config = LLMConfig(provider=LLMProvider.GEMINI, model="gemini-pro")
        api_config = ApiConfig(api_key="test-key", base_url="http://localhost:4000/v1")

        try:
            engine = GeminiEngine(config, api_config)
            assert engine is not None
        except LLMEngineError as e:
            if "openai" in str(e).lower():
                pytest.skip("openai пакет не установлен")
            raise


# ─────────────────────────── LLMAdapter (sync) ───────────────────

class TestLLMAdapter:
    def test_mock_call(self):
        config = LLMConfig(provider=LLMProvider.MOCK)
        adapter = LLMAdapter(config)

        response = adapter.call("test prompt")
        data = json.loads(response)

        assert "reason_short" in data
        assert isinstance(data, dict) and len(data) > 0

    def test_mock_with_cache(self):
        config = LLMConfig(provider=LLMProvider.MOCK)
        cache = InMemoryCache()
        adapter = LLMAdapter(config, cache=cache)

        response1 = adapter.call("test prompt")
        assert cache.size() == 1

        response2 = adapter.call("test prompt")
        assert response1 == response2
        assert cache.size() == 1

    def test_tokens_tracking(self):
        config = LLMConfig(provider=LLMProvider.MOCK)
        adapter = LLMAdapter(config)

        assert adapter.get_tokens_used() == 0
        adapter.call("test")
        assert adapter.get_tokens_used() == 0

        adapter.reset_tokens()
        assert adapter.get_tokens_used() == 0

    def test_cache_key_includes_model_params(self):
        config1 = LLMConfig(provider=LLMProvider.MOCK, model="gpt-4", temperature=0.7)
        config2 = LLMConfig(provider=LLMProvider.MOCK, model="gpt-3.5", temperature=0.7)
        config3 = LLMConfig(provider=LLMProvider.MOCK, model="gpt-4", temperature=0.3)

        adapter1 = LLMAdapter(config1)
        adapter2 = LLMAdapter(config2)
        adapter3 = LLMAdapter(config3)

        prompt = "same prompt"
        key1 = adapter1._cache_key(prompt)
        key2 = adapter2._cache_key(prompt)
        key3 = adapter3._cache_key(prompt)

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_cache_key_same_params_same_key(self):
        config = LLMConfig(provider=LLMProvider.MOCK, model="gpt-4", temperature=0.7)
        adapter1 = LLMAdapter(config)
        adapter2 = LLMAdapter(config)

        assert adapter1._cache_key("test") == adapter2._cache_key("test")

    def test_different_configs_no_cache_collision(self):
        cache = InMemoryCache()

        config_a = LLMConfig(provider=LLMProvider.MOCK, model="gpt-4")
        config_b = LLMConfig(provider=LLMProvider.MOCK, model="gpt-3.5")

        adapter_a = LLMAdapter(config_a, cache=cache)
        adapter_b = LLMAdapter(config_b, cache=cache)

        adapter_a.call("test prompt")
        adapter_b.call("test prompt")

        assert cache.size() == 2


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
        cache.set("k3", "v3")
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