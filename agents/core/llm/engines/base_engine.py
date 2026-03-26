"""
Абстрактный базовый класс для LLM engines.
Каждый провайдер (OpenAI, Claude, Gemini) наследует этот класс.

Исключения определены в agents.core.llm.exceptions (единственный source of truth).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Iterator

from agents.core.llm.exceptions import (
    LLMEngineError,
)


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
    """

    def __init__(self, config) -> None:
        """
        Args:
            config: LLMConfig из base_agent.py
        """
        self._config = config

    @property
    def config(self):
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
        Отправляет промпт в LLM и возвращает LLMResponse.

        Raises:
            LLMTransientError: временные ошибки (retry-able)
            LLMAuthenticationError: невалидный ключ
            LLMInvalidRequestError: некорректный запрос
            LLMEngineError: прочие ошибки
        """
        raise NotImplementedError

    def stream(self, prompt: str) -> Iterator[str]:
        """Потоковая генерация ответа (синхронная)."""
        response = self.call(prompt)
        yield response.text

    # ── Асинхронные методы ──

    @abstractmethod
    async def acall(self, prompt: str) -> LLMResponse:
        """Асинхронно отправляет промпт в LLM и возвращает LLMResponse."""
        raise NotImplementedError

    async def astream(self, prompt: str) -> AsyncIterator[str]:
        """Потоковая генерация ответа (асинхронная)."""
        response = await self.acall(prompt)
        yield response.text

    # ── Служебные методы ──

    def health_check(self) -> bool:
        """
        Проверка доступности провайдера.
        Использует минимальный промпт с инструкцией для экономии токенов.
        """
        try:
            self.call("health check: respond with 'ok'")
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