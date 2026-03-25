"""Gemini engine — алиас для OpenAICompatibleEngine."""

from agents.core.llm.engines.openai_compatible import OpenAICompatibleEngine


class GeminiEngine(OpenAICompatibleEngine):
    """Engine для Google Gemini через GPT-тунель."""
    pass