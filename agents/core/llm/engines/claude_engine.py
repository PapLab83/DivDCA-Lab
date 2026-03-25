"""Claude engine — алиас для OpenAICompatibleEngine."""

from agents.core.llm.engines.openai_compatible import OpenAICompatibleEngine


class ClaudeEngine(OpenAICompatibleEngine):
    """Engine для Anthropic Claude через GPT-тунель."""
    pass