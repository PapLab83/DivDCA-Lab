"""
Базовые классы для всех агентов.
Определяет интерфейсы и общую функциональность.

Декомпозиция:
    ResponseParser  — парсинг и валидация ответов LLM
    AgentLifecycle  — жизненный цикл (таймер, финализация, логирование)
    ErrorMapper     — маппинг исключений в AgentResult

Shared типы (Protocol'ы, Config, Context, Result, Enums) вынесены в types.py
для устранения циклических импортов.
"""
from __future__ import annotations

import asyncio
import logging

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Tuple

# Все shared типы импортируются из types.py — нет циклов
from agents.core.types import (
    AgentConfig,
    AgentContext,
    AgentMode,
    AgentResult,
    ApiConfig,
    AsyncLLMAdapterProtocol,
    CacheProtocol,
    FinancialAgentContext,
    LLMAdapterProtocol,
    LLMConfig,
    LLMProvider,
    PromptManagerProtocol,
    make_metadata,
)
from agents.core.agent_lifecycle import AgentLifecycle
from agents.core.response_parser import ResponseParser
from agents.core.error_mapper import ErrorMapper

if TYPE_CHECKING:
    from agents.core.profiles.profile import UserProfile

logger = logging.getLogger(__name__)


# Re-export всех типов для обратной совместимости.
# Код который импортирует из base_agent продолжает работать без изменений.
__all__ = [
    "AgentConfig",
    "AgentContext",
    "AgentMode",
    "AgentResult",
    "ApiConfig",
    "AsyncLLMAdapterProtocol",
    "BaseAgent",
    "CacheProtocol",
    "FinancialAgentContext",
    "LLMAdapterProtocol",
    "LLMConfig",
    "LLMProvider",
    "PromptManagerProtocol",
    "make_metadata",
]


class BaseAgent(ABC):
    """
    Абстрактный базовый класс для всех агентов.

    Использует композицию:
        _lifecycle    → AgentLifecycle  (таймер, финализация, логирование)
        _parser       → ResponseParser  (парсинг JSON, валидация полей)
        _error_mapper → ErrorMapper     (маппинг исключений → AgentResult)

    Опциональные зависимости:
        profile → UserProfile  (профиль агрессивности пользователя).
            Если передан — добавляется в metadata контекста при каждом execute().
            Агент может читать profile из context.metadata["profile"].

    Наследники переопределяют:
        _execute_internal(context) → AgentResult   [обязательно]
        required_fields() → Set[str]               [опционально]
        _setup(context)                             [опционально]
        _cleanup(context)                           [опционально]
    """

    def __init__(
        self,
        config: AgentConfig,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
        prompt_manager: Optional[PromptManagerProtocol] = None,
        profile: Optional[UserProfile] = None,
    ):
        """
        Args:
            config: конфигурация агента (провайдер, модель, кэш)
            llm_adapter: адаптер LLM (инжектируется Container'ом)
            prompt_manager: менеджер промптов (инжектируется Container'ом)
            profile: профиль агрессивности пользователя (опционально).
                Если передан — добавляется в metadata каждого AgentContext.
        """
        self.config = config
        self.llm_adapter = llm_adapter
        self.prompt_manager = prompt_manager
        self.profile = profile

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

        Переопределите в наследнике для автоматической валидации через ResponseParser:
            def required_fields(self) -> Set[str]:
                return {"reason_short", "reason_long", "confidence"}

        По умолчанию — пустое множество (валидация структуры отключена).
        """
        return set()

    # ── Внутренний хелпер: обогащение контекста профилем ──────────

    def _enrich_context_with_profile(self, context: AgentContext) -> AgentContext:
        """
        Добавляет UserProfile в metadata контекста если профиль задан
        и ещё не присутствует в metadata.

        Не мутирует исходный context — возвращает новый через dataclasses.replace.
        Новый metadata оборачивается в MappingProxyType автоматически
        через AgentContext.__post_init__.
        """
        if self.profile is not None and "profile" not in context.metadata:
            return replace(
                context,
                metadata=make_metadata({**context.metadata, "profile": self.profile}),
            )
        return context

    # ── public: sync ──────────────────────────────────────────────

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Синхронное выполнение агента.

        Если задан profile — добавляет его в context.metadata["profile"]
        перед передачей в _execute_internal.
        """
        context = self._enrich_context_with_profile(context)

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
        """
        Асинхронное выполнение агента.

        Если задан profile — добавляет его в context.metadata["profile"]
        перед передачей в _execute_internal_async.
        """
        context = self._enrich_context_with_profile(context)

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
        """
        Получение промпта через PromptManager.
        Возвращает (prompt, version).
        """
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
            "llm_adapter не поддерживает async: "
            "нет acall() и не реализует AsyncLLMAdapterProtocol"
        )

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Парсинг ответа от LLM через ResponseParser.
        Оставлен для обратной совместимости с наследниками.
        """
        return self._parser.parse(response)

    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """
        Валидация распарсенного результата.
        Переопределите required_fields() вместо этого метода.
        """
        return self._parser.validate_only(result)

    def _handle_error(self, error: Exception) -> AgentResult:
        """
        Обработка ошибок.
        Переопределите для кастомного маппинга конкретных исключений.
        """
        return self._error_mapper.handle(error, self.__class__.__name__)