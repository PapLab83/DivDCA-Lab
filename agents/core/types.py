"""
Shared типы и протоколы — единственный источник правды для всех core-компонентов.

Выделены из base_agent.py для устранения циклических импортов:
    base_agent.py ← agent_lifecycle.py ← base_agent.py  (цикл)

После выделения:
    types.py ← agent_lifecycle.py  (нет цикла)
    types.py ← response_parser.py  (нет цикла)
    types.py ← error_mapper.py     (нет цикла)
    types.py ← base_agent.py       (нет цикла)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Protocol, Tuple, runtime_checkable

from agents.core.llm.exceptions import LLMParseError  # noqa: F401  (re-export)


# ─────────────────────────── Protocols ────────────────────────────

@runtime_checkable
class LLMAdapterProtocol(Protocol):
    """Контракт для синхронных LLM адаптеров."""
    def call(self, prompt: str) -> str: ...


@runtime_checkable
class AsyncLLMAdapterProtocol(Protocol):
    """Контракт для асинхронных LLM адаптеров."""
    async def call(self, prompt: str) -> str: ...


@runtime_checkable
class PromptManagerProtocol(Protocol):
    """Контракт для менеджера промптов."""
    def get_prompt(self, task: str, **variables: Any) -> Tuple[str, str]: ...


@runtime_checkable
class CacheProtocol(Protocol):
    """Контракт для кэша."""
    def get(self, key: str) -> Optional[str]: ...
    def set(self, key: str, value: str) -> None: ...


# ─────────────────────────── Enums ────────────────────────────────

class AgentMode(StrEnum):
    """Режимы работы агента."""
    API = "api"


class LLMProvider(StrEnum):
    """Поддерживаемые LLM провайдеры."""
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    MOCK = "mock"


# ─────────────────────────── Helpers ──────────────────────────────

def make_metadata(data: Optional[Dict[str, Any]] = None) -> MappingProxyType:
    """
    Создаёт иммутабельный MappingProxyType для AgentContext.metadata
    и AgentResult.metadata.

    Использование:
        context = AgentContext(
            agent_id="run-001",
            task="event_generation",
            metadata=make_metadata({"ticker": "AAPL", "year": 2021}),
        )

        result = AgentResult(
            success=True,
            metadata=make_metadata({"agent_class": "MyAgent"}),
        )

    Args:
        data: исходный dict с данными. None → пустой proxy.

    Returns:
        MappingProxyType — read-only view, попытка записи бросает TypeError.
    """
    return MappingProxyType(data or {})


def merge_metadata(
    base: Mapping[str, Any],
    *updates: Optional[Dict[str, Any]],
) -> MappingProxyType:
    """
    Мерджит несколько dict'ов в новый иммутабельный MappingProxyType.

    Используется в AgentLifecycle.finalize() и ErrorMapper.handle()
    для добавления agent_class и extra_metadata к существующей metadata
    без мутации оригинала.

    Args:
        base: базовая mapping (например result.metadata)
        *updates: дополнительные dict'ы (None пропускается)

    Returns:
        Новый MappingProxyType со всеми слитыми данными.

    Пример:
        merged = merge_metadata(
            result.metadata,
            {"agent_class": "MyAgent"},
            extra_metadata,
        )
    """
    merged: Dict[str, Any] = dict(base)
    for update in updates:
        if update:
            merged.update(update)
    return MappingProxyType(merged)


# ─────────────────────────── Configs ──────────────────────────────

@dataclass
class LLMConfig:
    """Конфигурация LLM."""
    provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 1000
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                f"temperature должна быть в диапазоне [0, 2], получено: {self.temperature}"
            )
        if self.max_tokens <= 0:
            raise ValueError(
                f"max_tokens должно быть положительным, получено: {self.max_tokens}"
            )


@dataclass
class ApiConfig:
    """Конфигурация API подключения."""
    base_url: str = ""
    api_key: str = ""
    retries: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: int = 30

    def __repr__(self) -> str:
        if len(self.api_key) > 4:
            masked = self.api_key[:4] + "****"
        elif self.api_key:
            masked = "****"
        else:
            masked = "<empty>"
        return (
            f"ApiConfig(base_url={self.base_url!r}, api_key={masked!r}, "
            f"retries={self.retries}, timeout_seconds={self.timeout_seconds})"
        )


@dataclass
class AgentConfig:
    """
    Конфигурация агента.

    Attributes:
        mode: режим работы агента
        llm_config: конфигурация LLM провайдера
        api_config: конфигурация API подключения
        cache_enabled: включить кэш LLM ответов
        prompts_path: путь к директории с YAML-промптами.
            None → Container использует дефолтный путь (agents/prompts/).
            Передайте явный путь для переопределения через ENV или тесты:
                AgentConfig(prompts_path="/custom/prompts")
            Читается из ENV: PROMPTS_PATH
    """
    mode: AgentMode = AgentMode.API
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    api_config: ApiConfig = field(default_factory=ApiConfig)
    cache_enabled: bool = True
    prompts_path: Optional[str] = None


# ─────────────────────────── Context ──────────────────────────────

@dataclass(frozen=True)
class AgentContext:
    """
    Контекст выполнения агента.

    metadata — иммутабельный MappingProxyType:
        - попытка записи бросает TypeError (реальная защита, не только соглашение)
        - создавайте через make_metadata({"key": "value"})
        - или передавайте обычный dict — он будет автоматически обёрнут в __post_init__

    Пример:
        context = AgentContext(
            agent_id="run-001",
            task="event_generation",
            metadata=make_metadata({"ticker": "AAPL", "year": 2021}),
        )
    """
    agent_id: str
    task: str
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=MappingProxyType)

    def __post_init__(self) -> None:
        # Автоматически оборачиваем dict в MappingProxyType для удобства:
        #   AgentContext(metadata={"key": "val"})  — работает
        #   AgentContext(metadata=make_metadata(...))  — тоже работает
        if isinstance(self.metadata, dict):
            # frozen=True не позволяет присваивать напрямую — используем object.__setattr__
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))


@dataclass(frozen=True)
class FinancialAgentContext(AgentContext):
    """Контекст для финансовых агентов."""
    ticker: str = ""
    year: Optional[int] = None


# ─────────────────────────── Result ───────────────────────────────

@dataclass(frozen=True)
class AgentResult:
    """
    Результат работы агента.

    metadata — иммутабельный MappingProxyType:
        - попытка записи бросает TypeError (реальная защита)
        - создавайте через make_metadata({"key": "value"})
        - или передавайте обычный dict — он будет автоматически обёрнут в __post_init__
        - для слияния используйте merge_metadata(result.metadata, {"new_key": "val"})

    Пример:
        result = AgentResult(
            success=True,
            data={"reason_short": "..."},
            metadata=make_metadata({"agent_class": "EventGenerationAgent"}),
        )
    """
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    prompt_version: Optional[str] = None
    llm_response: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_ms: Optional[int] = None
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        # Автоматически оборачиваем dict в MappingProxyType для удобства:
        #   AgentResult(success=True, metadata={"agent_class": "MyAgent"})  — работает
        #   AgentResult(success=True, metadata=make_metadata(...))           — тоже работает
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))