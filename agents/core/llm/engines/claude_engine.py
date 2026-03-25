"""
Claude (Anthropic) engine.
TODO: реализовать полноценный вызов Anthropic API.
"""
import logging
from typing import Tuple

from agents.core.base_agent import LLMConfig
from agents.core.llm.engines.base_engine import BaseLLMEngine


logger = logging.getLogger(__name__)


class ClaudeEngine(BaseLLMEngine):
    """Engine для работы с Anthropic Claude API."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        logger.debug("ClaudeEngine создан для модели %s", config.model)

    def call(self, prompt: str) -> Tuple[str, int]:
        """
        Вызов Anthropic API.

        TODO: реализовать:
            client = anthropic.Anthropic(api_key=...)
            response = client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            tokens = response.usage.input_tokens + response.usage.output_tokens
            return text, tokens
        """
        raise NotImplementedError(
            "ClaudeEngine.call() ещё не реализован. "
            "Используйте LLMProvider.MOCK для тестирования."
        )