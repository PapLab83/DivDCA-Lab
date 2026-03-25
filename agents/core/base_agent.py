"""
Базовые классы для всех агентов.
Определяет интерфейсы и общую функциональность.
"""
import json
import logging
import re
import time

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Protocol, runtime_checkable
from dataclasses import dataclass, field


__all__ = [
    "LLMParseError",
    "LLMAdapterProtocol",
    "AsyncLLMAdapterProtocol",
    "PromptManagerProtocol",
    "AgentMode",
    "LLMProvider",
    "LLMConfig",
    "ApiConfig",
    "AgentConfig",
    "AgentContext",
    "FinancialAgentContext",
    "AgentResult",
    "BaseAgent",
]


logger = logging.getLogger(__name__)


class LLMParseError(Exception):
    """Ошибка парсинга ответа от LLM"""
    def __init__(self, message: str, raw_response: str):
        self.raw_response = raw_response
        super().__init__(message)


@runtime_checkable
class LLMAdapterProtocol(Protocol):
    """Контракт для LLM адаптеров"""
    def call(self, prompt: str) -> str: ...


@runtime_checkable
class AsyncLLMAdapterProtocol(Protocol):
    """Контракт для асинхронных LLM адаптеров"""
    async def call(self, prompt: str) -> str: ...


@runtime_checkable
class PromptManagerProtocol(Protocol):
    """Контракт для менеджера промптов"""
    def get_prompt(self, task: str, **variables) -> tuple[str, str]: ...
    # возвращает (prompt, version)


class AgentMode(str, Enum):
    """Режимы работы агента"""
    API = "api"


class LLMProvider(str, Enum):
    """Поддерживаемые LLM провайдеры"""
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    MOCK = "mock"


@dataclass
class LLMConfig:
    """Конфигурация LLM"""
    provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 1000
    timeout_seconds: int = 30

    def __post_init__(self):
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature должна быть в диапазоне [0, 2], получено: {self.temperature}")
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens должно быть положительным, получено: {self.max_tokens}")


@dataclass
class ApiConfig:
    """Конфигурация API подключения"""
    base_url: str = ""
    api_key: str = ""
    retries: int = 3
    timeout_seconds: int = 30


@dataclass
class AgentConfig:
    """Конфигурация агента"""
    mode: AgentMode = AgentMode.API
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    api_config: ApiConfig = field(default_factory=ApiConfig)
    cache_enabled: bool = True

    def __post_init__(self):
        if self.mode != AgentMode.API:
            raise NotImplementedError(f"Режим {self.mode} ещё не реализован. Доступен только: {AgentMode.API}")


@dataclass
class AgentContext:
    """Контекст выполнения агента"""
    agent_id: str
    task: str
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FinancialAgentContext(AgentContext):
    """Контекст для финансовых агентов"""
    ticker: str = ""
    year: Optional[int] = None


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


class BaseAgent(ABC):
    """Абстрактный базовый класс для всех агентов"""

    def __init__(
        self,
        config: AgentConfig,
        llm_adapter: Optional[LLMAdapterProtocol] = None
    ):
        self.config = config
        self.llm_adapter = llm_adapter
        self.prompt_manager: Optional[PromptManagerProtocol] = None
        logger.debug("Инициализирован агент %s", self.__class__.__name__)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(mode={self.config.mode})"

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Основной метод выполнения агента.
        Содержит обертку с замерами времени и обработкой ошибок.
        """
        start_time = time.time()
        result: Optional[AgentResult] = None

        try:
            logger.info(
                "Запуск агента %s (task=%s, agent_id=%s)",
                self.__class__.__name__, context.task, context.agent_id
            )

            self._setup(context)
            result = self._execute_internal(context)

            prompt_version = result.prompt_version
            if prompt_version is None:
                prompt_version = context.metadata.get('prompt_version')

            result = AgentResult(
                success=result.success,
                data=result.data,
                error=result.error,
                prompt_version=prompt_version,
                llm_response=result.llm_response,
                tokens_used=result.tokens_used,
                duration_ms=result.duration_ms,
                metadata={**result.metadata, 'agent_class': self.__class__.__name__},
            )

        except Exception as e:
            logger.error("Ошибка в агенте %s: %s", self.__class__.__name__, e, exc_info=True)
            try:
                result = self._handle_error(e)
            except Exception as inner:
                logger.critical("Ошибка в _handle_error: %s", inner, exc_info=True)
                result = AgentResult(
                    success=False,
                    error=f"Critical: {inner.__class__.__name__}: {inner}",
                    metadata={'agent_class': self.__class__.__name__},
                )

        finally:
            self._cleanup(context)
            if result is not None:
                duration_ms = int((time.time() - start_time) * 1000)
                result = AgentResult(
                    success=result.success,
                    data=result.data,
                    error=result.error,
                    prompt_version=result.prompt_version,
                    llm_response=result.llm_response,
                    tokens_used=result.tokens_used,
                    duration_ms=duration_ms,
                    metadata=result.metadata,
                )
                self._log_usage(result)

        return result

    @abstractmethod
    def _execute_internal(self, context: AgentContext) -> AgentResult:
        """
        Внутренняя реализация выполнения агента.
        Должна быть переопределена в наследниках.
        """
        pass

    def _setup(self, context: AgentContext) -> None:
        """Подготовка к выполнению (может быть переопределено)"""
        pass

    def _cleanup(self, context: AgentContext) -> None:
        """Очистка после выполнения (может быть переопределено)"""
        pass

    def _get_prompt(self, context: AgentContext, **variables) -> str:
        """
        Получение промпта через PromptManager.
        Должен быть инициализирован в наследнике.
        """
        if not self.prompt_manager:
            raise RuntimeError("prompt_manager не инициализирован")

        prompt, version = self.prompt_manager.get_prompt(
            task=context.task,
            **variables
        )
        context.metadata['prompt_version'] = version
        return prompt

    def _call_llm(self, prompt: str) -> str:
        """Вызов LLM адаптера"""
        if not self.llm_adapter:
            raise RuntimeError("llm_adapter не инициализирован")
        return self.llm_adapter.call(prompt)

    def _validate_result(self, result: Dict) -> bool:
        """
        Базовая валидация результата.
        Может быть переопределена в наследнике.
        """
        return bool(result)

    def _parse_response(self, response: str) -> Dict:
        """
        Парсинг ответа от LLM.
        Выбрасывает LLMParseError если ответ не является валидным JSON.
        """
        cleaned = response.strip()

        match = re.search(r'```(?:json)?\s*(.*?)\s*```', cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)

        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError as e:
            logger.error("Ошибка парсинга JSON: %s", e)
            logger.debug("Ответ: %s", response)
            raise LLMParseError(
                message=f"Ошибка парсинга JSON: {e}",
                raw_response=response
            ) from e

    def _handle_error(self, error: Exception) -> AgentResult:
        """Обработка ошибок"""
        return AgentResult(
            success=False,
            error=f"{error.__class__.__name__}: {str(error)}",
            metadata={'agent_class': self.__class__.__name__}
        )

    def _log_usage(self, result: AgentResult) -> None:
        """Логирование использования"""
        if result.success:
            logger.info(
                "Агент %s успешно выполнен за %dмс",
                self.__class__.__name__, result.duration_ms
            )
        else:
            logger.warning(
                "Агент %s завершился с ошибкой: %s",
                self.__class__.__name__, result.error
            )