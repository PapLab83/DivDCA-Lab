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
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable

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
    """Конфигурация агента."""
    mode: AgentMode = AgentMode.API
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    api_config: ApiConfig = field(default_factory=ApiConfig)
    cache_enabled: bool = True


# ─────────────────────────── Context ──────────────────────────────

@dataclass(frozen=True)
class AgentContext:
    """Контекст выполнения агента (иммутабельный по соглашению)."""
    agent_id: str
    task: str
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinancialAgentContext(AgentContext):
    """Контекст для финансовых агентов."""
    ticker: str = ""
    year: Optional[int] = None


# ─────────────────────────── Result ───────────────────────────────

@dataclass(frozen=True)
class AgentResult:
    """Результат работы агента."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    prompt_version: Optional[str] = None
    llm_response: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)