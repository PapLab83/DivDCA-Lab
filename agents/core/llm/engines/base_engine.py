"""
Абстрактный базовый класс для LLM engines.
Каждый провайдер (OpenAI, Claude, Gemini) наследует этот класс.
"""
from abc import ABC, abstractmethod
from typing import Tuple

from agents.core.base_agent import LLMConfig


class BaseLLMEngine(ABC):
    """Базовый engine для LLM провайдеров."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def call(self, prompt: str) -> Tuple[str, int]:
        """
        Отправляет промпт в LLM и возвращает ответ.

        Args:
            prompt: текст промпта

        Returns:
            Tuple[response_text, tokens_used]
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.config.model})"