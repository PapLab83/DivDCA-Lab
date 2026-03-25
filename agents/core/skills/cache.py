"""
Google Gemini engine.
TODO: реализовать полноценный вызов Google Generative AI API.
"""
import logging
from typing import Tuple

from agents.core.base_agent import LLMConfig
from agents.core.llm.engines.base_engine import BaseLLMEngine


logger = logging.getLogger(__name__)


class GeminiEngine(BaseLLMEngine):
    """Engine для работы с Google Gemini API."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        logger.debug("GeminiEngine создан для модели %s", config.model)

    def call(self, prompt: str) -> Tuple[str, int]:
        """
        Вызов Google Generative AI API.

        TODO: реализовать:
            import google.generativeai as genai
            genai.configure(api_key=...)
            model = genai.GenerativeModel(self.config.model)
            response = model.generate_content(prompt)
            text = response.text
            tokens = response.usage_metadata.total_token_count
            return text, tokens
        """
        raise NotImplementedError(
            "GeminiEngine.call() ещё не реализован. "
            "Используйте LLMProvider.MOCK для тестирования."
        )