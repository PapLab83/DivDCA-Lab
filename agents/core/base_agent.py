"""
Базовые классы для всех агентов.
Определяет интерфейсы и общую функциональность.

Декомпозиция:
    ResponseParser  — парсинг и валидация ответов LLM
    AgentLifecycle  — жизненный цикл (таймер, финализация, логирование)
    ErrorMapper     — маппинг исключений в AgentResult
"""
import asyncio
import logging

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional, Dict, Any, Protocol, Set, Tuple, runtime_checkable

from agents.core.llm.exceptions import LLMParseError


logger = logging.getLogger(__name__)


# ─────────────────────────── Protocols ────────────────────────────

@runtime_checkable
class LLMAdapterProtocol(Protocol):
    """Контракт для синхронных LLM адаптеров"""
    def call(self, prompt: str) -> str: ...


@runtime_checkable
class AsyncLLMAdapterProtocol(Protocol):
    """Контракт для асинхронных LLM адаптеров."""
    async def call(self, prompt: str) -> str: ...


@runtime_checkable
class PromptManagerProtocol(Protocol):
    """Контракт для менеджера промптов"""
    def get_prompt(self, task: str, **variables: Any) -> Tuple[str, str]: ...


@runtime_checkable
class CacheProtocol(Protocol):
    """Контракт для кэша"""
    def get(self, key: str) -> Optional[str]: ...
    def set(self, key: str, value: str) -> None: ...


# ─────────────────────────── Enums ────────────────────────────────

class AgentMode(StrEnum):
    """Режимы работы агента"""
    API = "api"


class LLMProvider(StrEnum):
    """Поддерживаемые LLM провайдеры"""
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    MOCK = "mock"


# ─────────────────────────── Configs ──────────────────────────────

@dataclass
class LLMConfig:
    """Конфигурация LLM"""
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
    """Конфигурация API подключения"""
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
    """Конфигурация агента"""
    mode: AgentMode = AgentMode.API
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    api_config: ApiConfig = field(default_factory=ApiConfig)
    cache_enabled: bool = True

    def __post_init__(self) -> None:
        if self.mode != AgentMode.API:
            raise NotImplementedError(
                f"Режим {self.mode} ещё не реализован. Доступен только: {AgentMode.API}"
            )


# ─────────────────────────── Context ──────────────────────────────

@dataclass
class AgentContext:
    """Контекст выполнения агента (иммутабельный по соглашению)"""
    agent_id: str
    task: str
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FinancialAgentContext(AgentContext):
    """Контекст для финансовых агентов"""
    ticker: str = ""
    year: Optional[int] = None


# ─────────────────────────── Result ───────────────────────────────

@dataclass(frozen=True)
class AgentResult:
    """Результат работы агента"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    prompt_version: Optional[str] = None
    llm_response: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────── BaseAgent ────────────────────────────

class BaseAgent(ABC):
    """
    Абстрактный базовый класс для всех агентов.

    Использует композицию:
        _lifecycle  → AgentLifecycle  (тайм��р, финализация, логирование)
        _parser     → ResponseParser  (парсинг JSON, валидация полей)
        _error_mapper → ErrorMapper   (маппинг исключений → AgentResult)

    Наследники переопределяют:
        _execute_internal(context) → AgentResult   [обязательно]
        _setup(context)                             [опционально]
        _cleanup(context)                           [опционально]
        required_fields() → Set[str]               [опционально]
    """

    def __init__(
        self,
        config: AgentConfig,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
        prompt_manager: Optional[PromptManagerProtocol] = None,
    ):
        self.config = config
        self.llm_adapter = llm_adapter
        self.prompt_manager = prompt_manager

        # ── Композиционные компоненты ──
        # Импорт здесь чтобы избежать циклических зависимостей на уровне модуля
        from agents.core.agent_lifecycle import AgentLifecycle
        from agents.core.response_parser import ResponseParser
        from agents.core.error_mapper import ErrorMapper

        self._lifecycle = AgentLifecycle(
            agent_class_name=self.__class__.__name__,
        )
        self._parser = ResponseParser(
            required_fields=self.required_fields(),
        )
        self._error_mapper = ErrorMapper()

        logger.debug("Инициализирован агент %s", self.__class__.__name__)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(mode={self.config.mode})"

    # ── Переопределяемые свойства ─────────────────────────────────

    def required_fields(self) -> Set[str]:
        """
        Обязательные поля в ответе LLM.

        Переопределите в наследнике для автоматической валидации:
            def required_fields(self) -> Set[str]:
                return {"reason_short", "reason_long", "confidence"}

        По умолчанию — пустое множество (валидация структуры отключена).
        """
        return set()

    # ── public: sync ──────────────────────────────────────────────

    def execute(self, context: AgentContext) -> AgentResult:
        """Синхронное выполнение агента."""
        start_time = self._lifecycle.start()
        result = AgentResult(success=False, error="Unexpected")
        try:
            self._lifecycle.run_setup(context, self._setup)
            result = self._execute_internal(context)
        except Exception as e:
            result = self._error_mapper.handle(e, self.__class__.__name__)
        finally:
            self._lifecycle.run_cleanup(context, self._cleanup)
            result = self._lifecycle.finalize(context, start_time, result)
        return result

    # ── public: async ─────────────────────────────────────────────

    async def execute_async(self, context: AgentContext) -> AgentResult:
        """Асинхронное выполнение агента."""
        start_time = self._lifecycle.start()
        result = AgentResult(success=False, error="Unexpected")
        try:
            self._lifecycle.run_setup(context, self._setup)
            result = await self._execute_internal_async(context)
        except Exception as e:
            result = self._error_mapper.handle(e, self.__class__.__name__)
        finally:
            self._lifecycle.run_cleanup(context, self._cleanup)
            result = self._lifecycle.finalize(context, start_time, result)
        return result

    # ── abstract ──────────────────────────────────────────────────

    @abstractmethod
    def _execute_internal(self, context: AgentContext) -> AgentResult:
        """Внутренняя реализация — переопределяется в наследниках."""
        ...

    async def _execute_internal_async(self, context: AgentContext) -> AgentResult:
        """
        Асинхронная внутренняя реализация.
        По умолчанию запускает синхронный метод в thread pool.
        Переопределите для настоящей async-логики.
        """
        return await asyncio.to_thread(self._execute_internal, context)

    # ── hooks ─────────────────────────────────────────────────────

    def _setup(self, context: AgentContext) -> None:
        """Подготовка к выполнению. Переопределите при необходимости."""

    def _cleanup(self, context: AgentContext) -> None:
        """Очистка после выполнения. Переопределите при необходимости."""

    # ── helpers ───────────────────────────────────────────────────

    def _get_prompt(self, context: AgentContext, **variables: Any) -> Tuple[str, str]:
        """Получение промпта через PromptManager. Возвращает (prompt, version)."""
        if not self.prompt_manager:
            raise RuntimeError("prompt_manager не инициализирован")
        return self.prompt_manager.get_prompt(task=context.task, **variables)

    def _call_llm(self, prompt: str) -> str:
        """Синхронный вызов LLM адаптера."""
        if not self.llm_adapter:
            raise RuntimeError("llm_adapter не инициализирован")
        return self.llm_adapter.call(prompt)

    async def _call_llm_async(self, prompt: str) -> str:
        """Асинхронный вызов LLM адаптера."""
        if not self.llm_adapter:
            raise RuntimeError("llm_adapter не инициализирован")
        if hasattr(self.llm_adapter, "acall"):
            return await self.llm_adapter.acall(prompt)
        if isinstance(self.llm_adapter, AsyncLLMAdapterProtocol):
            return await self.llm_adapter.call(prompt)
        raise RuntimeError(
            "llm_adapter не поддерживает async: нет acall() и не реализует AsyncLLMAdapterProtocol"
        )

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Парсинг ответа от LLM через ResponseParser.

        Делегирует в self._parser.
        Оставлен для обратной совместимости с наследниками,
        которые вызывают super()._parse_response().
        """
        return self._parser.parse(response)

    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """
        Валидация распарсенного результата.

        Делегирует в self._parser.validate_only().
        Переопределите required_fields() вместо этого метода.
        """
        return self._parser.validate_only(result)

    def _handle_error(self, error: Exception) -> AgentResult:
        """
        Обработка ошибок.

        Делегирует в self._error_mapper.
        Переопределите для кастомного маппинга конкретных исключений.
        """
        return self._error_mapper.handle(error, self.__class__.__name__)