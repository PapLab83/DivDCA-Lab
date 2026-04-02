"""
Gemini engine — OpenAI-compatible прокси.

⚠️ ТРЕБУЕТ OpenAI-compatible прокси (LiteLLM, OneAPI и т.д.).
Нативный Google Generative AI API НЕ поддерживается напрямую.

Пример настройки:
    API_BASE_URL=http://localhost:4000/v1  # LiteLLM
    LLM_PROVIDER=gemini
    LLM_MODEL=gemini-pro
"""

from agents.core.base_agent import ApiConfig, LLMConfig
from agents.core.llm.engines.openai_compatible import OpenAICompatibleEngine
from agents.core.llm.exceptions import LLMEngineError


class GeminiEngine(OpenAICompatibleEngine):
    """
    Engine для Google Gemini через OpenAI-compatible прокси.

    Не работает напрямую с Google Generative AI API.
    Требуется указать API_BASE_URL, указывающий на прокси
    (LiteLLM, OneAPI или аналог).
    """

    def __init__(self, config: LLMConfig, api_config: ApiConfig) -> None:
        if not api_config.base_url:
            raise LLMEngineError(
                "GeminiEngine требует OpenAI-compatible прокси. "
                "Укажите API_BASE_URL (например, LiteLLM: http://localhost:4000/v1). "
                "Нативный Google AI API не поддерживается."
            )
        super().__init__(config, api_config)