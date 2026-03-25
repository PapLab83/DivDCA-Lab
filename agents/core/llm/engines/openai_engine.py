"""
OpenAI engine.
TODO: реализовать полноценный вызов OpenAI API.
"""
import logging
from typing import Tuple

from agents.core.base_agent import LLMConfig
from agents.core.llm.engines.base_engine import BaseLLMEngine


logger = logging.getLogger(__name__)


class OpenAIEngine(BaseLLMEngine):
    """Engine для работы с OpenAI API (GPT-4, GPT-3.5 и т.д.)."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        # TODO: инициализировать openai.OpenAI(api_key=...)
        logger.debug("OpenAIEngine создан для модели %s", config.model)

    def call(self, prompt: str) -> Tuple[str, int]:
        """
        Вызов OpenAI API.

        TODO: реализовать:
            client = openai.OpenAI(api_key=...)
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            text = response.choices[0].message.content
            tokens = response.usage.total_tokens
            return text, tokens
        """
        raise NotImplementedError(
            "OpenAIEngine.call() ещё не реализован. "
            "Используйте LLMProvider.MOCK для тестирования."
        )