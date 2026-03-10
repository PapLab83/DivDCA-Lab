"""
Базовые классы для всех агентов.
Определяет интерфейсы и общую функциональность.
"""
import json
import logging
import time

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime


logger = logging.getLogger(__name__)


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


@dataclass
class AgentConfig:
    """Конфигурация агента"""
    mode: AgentMode = AgentMode.LOCAL
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    api_config: Dict[str, Any] = field(default_factory=dict)
    cache_enabled: bool = True


@dataclass
class AgentContext:
    """Контекст выполнения агента"""
    agent_id: str
    task: str
    ticker: str
    year: int
    start_time: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


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

    def __init__(self, config: AgentConfig, llm_adapter=None):
        self.config = config
        self.llm_adapter = llm_adapter
        self.context: Optional[AgentContext] = None
        self.prompt_manager = None
        logger.debug(f"Инициализирован агент {self.__class__.__name__}")

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Основной метод выполнения агента.
        Содержит обертку с замерами времени и обработкой ошибок.
        """
        self.context = context
        start_time = time.time()

        try:
            logger.info(f"Запуск агента {self.__class__.__name__} "
                        f"(task_id={context.task_id}, ticker={context.ticker}, year={context.year})")

            self._setup()
            result = self._execute_internal(context)
            self._cleanup()

            # Добавляем метрики
            result.duration_ms = int((time.time() - start_time) * 1000)
            result.metadata['agent_class'] = self.__class__.__name__

            self._log_usage(result)
            return result

        except Exception as e:
            logger.error(f"Ошибка в агенте {self.__class__.__name__}: {e}", exc_info=True)
            return self._handle_error(e)

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
        # Сохраняем версию в контекст для логирования
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
        return bool(result)  # простая проверка на непустой результат

    def _parse_response(self, response: str) -> Dict:
        """Парсинг ответа от LLM"""
        try:
            # Очищаем ответ от возможных markdown-оберток
            if response.startswith("```json"):
                response = response.replace("```json", "").replace("```", "")
            elif response.startswith("```"):
                response = response.replace("```", "")

            return json.loads(response.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            logger.debug(f"Ответ: {response}")
            return {"error": "invalid_json", "raw_response": response}

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
            logger.info(f"Агент {self.__class__.__name__} успешно выполнен "
                        f"за {result.duration_ms}мс")
        else:
            logger.warning(f"Агент {self.__class__.__name__} завершился с ошибкой: "
                           f"{result.error}")
