"""
Базовые классы для всех агентов.
Определяет интерфейсы и общую функциональность.
"""
import json
import logging
import time

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


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
class PromptManagerProtocol(Protocol):
    """Контракт для менеджера промптов"""
    def get_prompt(self, task: str, **variables) -> tuple[str, str]: ...
    # возвращает (prompt, version)


class AgentMode(str, Enum):
    """Режимы работы агента"""
    LOCAL = "local"  # локальный вызов
    API = "api"  # вызов через API
    MOCK = "mock"  # тестовый режим с заглушками


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
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError(f"temperature должна быть в диапазоне [0, 1], получено: {self.temperature}")
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
    mode: AgentMode = AgentMode.LOCAL
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    api_config: ApiConfig = field(default_factory=ApiConfig)
    cache_enabled: bool = True


@dataclass
class AgentContext:
    """Контекст выполнения агента"""
    agent_id: str
    task: str
    start_time: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FinancialAgentContext(AgentContext):
    """Контекст для финансовых агентов"""
    ticker: str = ""
    year: int = 0


@dataclass
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
        self.context: Optional[AgentContext] = None
        self.prompt_manager: Optional[PromptManagerProtocol] = None
        logger.debug(f"Инициализирован агент {self.__class__.__name__}")

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Основной метод выполнения агента.
        Содержит обертку с замерами времени и обработкой ошибок.
        """
        self.context = context
        start_time = time.time()
        result: Optional[AgentResult] = None

        try:
            logger.info(
                f"Запуск агента {self.__class__.__name__} "
                f"(task={context.task}, agent_id={context.agent_id})"  # ← исправлен task_id → task
            )

            self._setup()
            result = self._execute_internal(context)

            # Явное копирование prompt_version из metadata контекста в результат
            if result.prompt_version is None:
                result.prompt_version = context.metadata.get('prompt_version')

            result.metadata['agent_class'] = self.__class__.__name__

        except Exception as e:
            logger.error(f"Ошибка в агенте {self.__class__.__name__}: {e}", exc_info=True)
            result = self._handle_error(e)

        finally:
            # _cleanup() выполняется всегда — даже если было исключение
            self._cleanup()
            if result is not None:
                result.duration_ms = int((time.time() - start_time) * 1000)
                self._log_usage(result)

        return result

    @abstractmethod
    def _execute_internal(self, context: AgentContext) -> AgentResult:
        """
        Внутренняя реализация выполнения агента.
        Должна быть переопределена в наследниках.
        """
        pass

    def _setup(self) -> None:
        """Подготовка к выполнению (может быть переопределено)"""
        pass

    def _cleanup(self) -> None:
        """Очистка после выполнения (может быть переопределено)"""
        pass

    def _get_prompt(self, **variables) -> str:
        """
        Получение промпта через PromptManager.
        Должен быть инициализирован в наследнике.
        """
        if not self.prompt_manager:
            raise NotImplementedError("prompt_manager не инициализирован")

        prompt, version = self.prompt_manager.get_prompt(
            task=self.context.task if self.context else "unknown",
            **variables
        )
        # Сохраняем версию в контекст для последующего копирования в result
        if self.context:
            self.context.metadata['prompt_version'] = version
        return prompt

    def _call_llm(self, prompt: str) -> str:
        if not self.llm_adapter:
            raise NotImplementedError("llm_adapter не инициализирован")
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

        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").removesuffix("```")
        elif cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removesuffix("```")

        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            logger.debug(f"Ответ: {response}")
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
                f"Агент {self.__class__.__name__} успешно выполнен "
                f"за {result.duration_ms}мс"
            )
        else:
            logger.warning(
                f"Агент {self.__class__.__name__} завершился с ошибкой: "
                f"{result.error}"
            )
