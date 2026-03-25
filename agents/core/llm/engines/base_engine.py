"""
Абстрактный базовый класс для LLM engines.
Каждый провайдер (OpenAI, Claude, Gemini) наследует этот класс.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Iterator, Optional


# ─────────────────────────────────────────────
# Исключения
# ─────────────────────────────────────────────

class LLMEngineError(Exception):
    """Базовая ошибка LLM engine."""


class LLMConnectionError(LLMEngineError):
    """Ошибка соединения с провайдером."""


class LLMRateLimitError(LLMEngineError):
    """Превышен лимит запросов."""


class LLMAuthenticationError(LLMEngineError):
    """Ошибка аутентификации (невалидный API-ключ)."""


class LLMInvalidRequestError(LLMEngineError):
    """Некорректный запрос (prompt слишком длинный и т.д.)."""


class LLMTimeoutError(LLMEngineError):
    """Таймаут запроса."""


# ─────────────────────────────────────────────
# Конфигурация
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class LLMConfig:
    """
    Конфигурация LLM провайдера.

    Attributes:
        model: название модели (e.g. 'gpt-4o', 'claude-sonnet-4-20250514')
        api_key: API-ключ провайдера
        temperature: температура генерации (0.0 — детерминированно, 1.0 — креативно)
        max_tokens: максимальное количество токенов в ответе
        timeout: таймаут запроса в секундах
        max_retries: количество повторных попыток при ошибке
        base_url: кастомный URL API (для прокси / self-hosted)
        extra: дополнительные параметры провайдера
    """

    model: str
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 30.0
    max_retries: int = 3
    base_url: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise ValueError("model не может быть пустым")
        if not self.api_key or not self.api_key.strip():
            raise ValueError("api_key не может быть пустым")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature должна быть в диапазоне [0.0, 2.0], получено: {self.temperature}")
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens должен быть > 0, получено: {self.max_tokens}")
        if self.timeout <= 0:
            raise ValueError(f"timeout должен быть > 0, получено: {self.timeout}")
        if self.max_retries < 0:
            raise ValueError(f"max_retries должен быть >= 0, получено: {self.max_retries}")


# ─────────────────────────────────────────────
# Ответ LLM
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class LLMResponse:
    """
    Структурированный ответ от LLM.

    Attributes:
        text: текст ответа модели
        tokens_used: общее количество использованных токенов
        prompt_tokens: токены промпта
        completion_tokens: токены ответа
        model: модель, которая сгенерировала ответ
        finish_reason: причина завершения ('stop', 'length', 'error')
    """

    text: str
    tokens_used: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    finish_reason: str = "stop"


# ─────────────────────────────────────────────
# Базовый engine
# ─────────────────────────────────────────────

class BaseLLMEngine(ABC):
    """
    Базовый engine для LLM провайдеров.

    Каждый провайдер (OpenAI, Claude, Gemini и т.д.) наследует этот класс
    и реализует синхронные и/или асинхронные методы.

    Пример использования::

        class OpenAIEngine(BaseLLMEngine):
            def call(self, prompt: str) -> LLMResponse:
                # реализация
                ...

            async def acall(self, prompt: str) -> LLMResponse:
                # реализация
                ...

        config = LLMConfig(model="gpt-4o", api_key="sk-...")
        engine = OpenAIEngine(config)
        response = engine.call("Привет!")
        print(response.text, response.tokens_used)
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    @property
    def config(self) -> LLMConfig:
        """Конфигурация engine (read-only)."""
        return self._config

    @property
    def model_name(self) -> str:
        """Короткий доступ к имени модели."""
        return self._config.model

    # ── Синхронные методы ──

    @abstractmethod
    def call(self, prompt: str) -> LLMResponse:
        """
        Отправляет промпт в LLM и возвращает ответ.

        Args:
            prompt: текст промпта

        Returns:
            LLMResponse с текстом и метаданными

        Raises:
            LLMConnectionError: ошибка соединения
            LLMRateLimitError: превышен лимит
            LLMAuthenticationError: невалидный ключ
            LLMInvalidRequestError: некорректный запрос
            LLMTimeoutError: таймаут
            LLMEngineError: прочие ошибки
        """
        raise NotImplementedError

    def stream(self, prompt: str) -> Iterator[str]:
        """
        Потоковая генерация ответа (синхронная).

        Args:
            prompt: текст промпта

        Yields:
            Части текста по мере генерации

        Raises:
            LLMEngineError: при ошибках
        """
        response = self.call(prompt)
        yield response.text

    # ── Асинхронные методы ──

    @abstractmethod
    async def acall(self, prompt: str) -> LLMResponse:
        """
        Асинхронно отправляет промпт в LLM и возвращает ответ.

        Args:
            prompt: текст промпта

        Returns:
            LLMResponse с текстом и метаданными

        Raises:
            LLMEngineError: при ошибках
        """
        raise NotImplementedError

    async def astream(self, prompt: str) -> AsyncIterator[str]:
        """
        Потоковая генерация ответа (асинхронная).

        Args:
            prompt: текст промпта

        Yields:
            Части текста по мере генерации

        Raises:
            LLMEngineError: при ошибках
        """
        response = await self.acall(prompt)
        yield response.text

    # ── Служебные методы ──

    def health_check(self) -> bool:
        """
        Проверка доступности провайдера.

        Returns:
            True если провайдер доступен
        """
        try:
            self.call("ping")
            return True
        except LLMEngineError:
            return False

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"model={self._config.model!r}, "
            f"temperature={self._config.temperature}, "
            f"max_tokens={self._config.max_tokens})"
        )

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{self._config.model}]"