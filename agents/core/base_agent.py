"""
Базовые классы для всех агентов.
Определяет интерфейсы и общую функциональность.
"""
import json
import logging
import re
import time
import asyncio

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional, Dict, Any, Protocol, Tuple, runtime_checkable

from agents.core.llm.exceptions import (
    LLMParseError,
)


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
    # возвращает (prompt, version)


@runtime_checkable
class CacheProtocol(Protocol):
    """Контракт для кэша"""

    def get(self, key: str) -> Optional[str]: ...

    def set(self, key: str, value: str) -> None: ...


# ─────────────────────────── Enums ────────────────────────────────

class AgentMode(str, StrEnum):
    """Режимы работы агента"""
    API = "api"


class LLMProvider(str, StrEnum):
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
    """Абстрактный базовый класс для всех агентов"""

    def __init__(
        self,
        config: AgentConfig,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
        prompt_manager: Optional[PromptManagerProtocol] = None,
    ):
        self.config = config
        self.llm_adapter = llm_adapter
        self.prompt_manager = prompt_manager
        logger.debug("Инициализирован агент %s", self.__class__.__name__)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(mode={self.config.mode})"



    # ── private: общая обёртка ────────────────────────────────────

    def _wrap_result(
            self,
            context: AgentContext,
            start_time: float,
            result: AgentResult,
    ) -> AgentResult:
        """Добавляет метаданные, duration, логирует. Вызывается из finally."""
        self._cleanup(context)
        duration_ms = int((time.monotonic() - start_time) * 1000)
        result = replace(
            result,
            duration_ms=duration_ms,
            metadata={**result.metadata, "agent_class": self.__class__.__name__},
        )
        self._log_usage(result)
        return result

    def _safe_handle_error(self, error: Exception) -> AgentResult:
        """handle_error с защитой от исключений внутри самого handler."""
        try:
            return self._handle_error(error)
        except Exception as inner:
            logger.critical("Ошибка в _handle_error: %s", inner, exc_info=True)
            return AgentResult(
                success=False,
                error=f"Critical: {inner.__class__.__name__}: {inner}",
            )

    # ── public: sync ──────────────────────────────────────────────

    def execute(self, context: AgentContext) -> AgentResult:
        """Синхронное выполнение агента."""
        start_time = time.monotonic()
        result = AgentResult(success=False, error="Unexpected")  # default
        try:
            logger.info(
                "Запуск агента %s (task=%s, agent_id=%s)",
                self.__class__.__name__, context.task, context.agent_id,
            )
            self._setup(context)
            result = self._execute_internal(context)
        except Exception as e:
            logger.error("Ошибка в агенте %s: %s", self.__class__.__name__, e, exc_info=True)
            result = self._safe_handle_error(e)
        finally:
            result = self._wrap_result(context, start_time, result)
        return result

    # ── public: async ─────────────────────────────────────────────

    async def execute_async(self, context: AgentContext) -> AgentResult:
        """Асинхронное выполнение агента."""
        start_time = time.monotonic()
        result = AgentResult(success=False, error="Unexpected")
        try:
            logger.info(
                "Async запуск агента %s (task=%s, agent_id=%s)",
                self.__class__.__name__, context.task, context.agent_id,
            )
            self._setup(context)
            result = await self._execute_internal_async(context)
        except Exception as e:
            logger.error("Ошибка в агенте %s: %s", self.__class__.__name__, e, exc_info=True)
            result = self._safe_handle_error(e)
        finally:
            result = self._wrap_result(context, start_time, result)
        return result

    # ── abstract ──────────────────────────────────────────────────

    @abstractmethod
    def _execute_internal(self, context: AgentContext) -> AgentResult:
        """Внутренняя реализация — переопределяется в наследниках."""
        ...

    async def _execute_internal_async(self, context: AgentContext) -> AgentResult:
        """
        Асинхронная внутренняя реализация.
        По умолчанию запускает синхронный метод в thread pool,
        чтобы не блокировать event loop.
        Переопределите для настоящей async-логики.
        """
        return await asyncio.to_thread(self._execute_internal, context)

    # ── hooks (переопределяемые) ──────────────────────────────────

    def _setup(self, context: AgentContext) -> None:
        """Подготовка к выполнению."""

    def _cleanup(self, context: AgentContext) -> None:
        """Очистка после выполнения."""

    # ── helpers ────────────────────────────────────────────────────

    def _get_prompt(self, context: AgentContext, **variables: Any) -> Tuple[str, str]:
        """
        Получение промпта через PromptManager.
        Возвращает (prompt, version) без мутации context.
        """
        if not self.prompt_manager:
            raise RuntimeError("prompt_manager не инициализирован")

        prompt, version = self.prompt_manager.get_prompt(
            task=context.task,
            **variables,
        )
        return prompt, version

    def _call_llm(self, prompt: str) -> str:
        """Вызов LLM адаптера."""
        if not self.llm_adapter:
            raise RuntimeError("llm_adapter не инициализирован")

        return self.llm_adapter.call(prompt)

    async def _call_llm_async(self, prompt: str) -> str:
        """Асинхронный вызов LLM адаптера."""
        if not self.llm_adapter:
            raise RuntimeError("llm_adapter не инициализирован")

        # Предпочитаем acall если доступен (LLMAdapter),
        # fallback на AsyncLLMAdapterProtocol.call
        if hasattr(self.llm_adapter, "acall"):
            return await self.llm_adapter.acall(prompt)

        if isinstance(self.llm_adapter, AsyncLLMAdapterProtocol):
            return await self.llm_adapter.call(prompt)

        raise RuntimeError(
            "llm_adapter не поддерживает async: нет acall() и не реализует AsyncLLMAdapterProtocol"
        )

    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """
        Валидация распарсенного результата.
        Переопределите в наследниках для проверки обязательных полей.
        """
        return bool(result)

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Парсинг ответа от LLM.
        Поддерживает извлечение JSON из markdown-блоков.
        Автоматически вызывает _validate_result.
        """
        cleaned = response.strip()

        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)

        try:
            parsed: Dict[str, Any] = json.loads(cleaned.strip())
        except json.JSONDecodeError as e:
            logger.error("Ошибка парсинга JSON: %s", e)
            logger.debug("Ответ: %s", response)
            raise LLMParseError(
                message=f"Ошибка парсинга JSON: {e}",
                raw_response=response,
            ) from e

        if not self._validate_result(parsed):
            raise LLMParseError(
                message="Результат не прошёл валидацию",
                raw_response=response,
            )

        return parsed

    def _handle_error(self, error: Exception) -> AgentResult:
        """Обработка ошибок — может быть переопределена."""
        return AgentResult(
            success=False,
            error=f"{error.__class__.__name__}: {error}",
            metadata={"agent_class": self.__class__.__name__},
        )

    def _log_usage(self, result: AgentResult) -> None:
        """Логирование результата выполнения."""
        duration = result.duration_ms if result.duration_ms is not None else -1
        if result.success:
            logger.info(
                "Агент %s успешно выполнен за %dмс",
                self.__class__.__name__, duration,
            )
        else:
            logger.warning(
                "Агент %s завершился с ошибкой за %dмс: %s",
                self.__class__.__name__, duration, result.error,
            )