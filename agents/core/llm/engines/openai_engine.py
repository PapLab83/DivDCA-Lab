"""OpenAI engine — алиас для OpenAICompatibleEngine."""

from agents.core.llm.engines.openai_compatible import OpenAICompatibleEngine


class OpenAIEngine(OpenAICompatibleEngine):
    """Engine для OpenAI (GPT-4o, GPT-4, GPT-3.5)."""
    pass