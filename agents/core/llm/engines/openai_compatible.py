"""
Универсальный OpenAI-совместимый LLM engine.
"""

import logging
from typing import AsyncIterator, Iterator

try:
    import openai
    from openai import AsyncOpenAI, OpenAI

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from agents.core.base_agent import ApiConfig, LLMConfig
from agents.core.llm.engines.base_engine import BaseLLMEngine, LLMResponse
from agents.core.llm.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMEngineError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleEngine(BaseLLMEngine):
    """
    Универсальный engine для любого OpenAI-совместимого API.
    """

    def __init__(self, config: LLMConfig, api_config: ApiConfig) -> None:
        """
        Args:
            config: LLMConfig из base_agent.py
            api_config: ApiConfig с ключом и base_url
        """
        super().__init__(config)
        self._api_config = api_config

        if not HAS_OPENAI:
            raise LLMEngineError(
                "Пакет 'openai' не установлен. Установите: pip install openai"
            )

        client_kwargs = self._build_client_kwargs()

        self._client: OpenAI = OpenAI(**client_kwargs)
        self._async_client: AsyncOpenAI = AsyncOpenAI(**client_kwargs)

        logger.debug(
            "OpenAICompatibleEngine создан: model=%s",
            config.model,
        )

    # ─────────────────────────────────────────────
    # Синхронные методы
    # ─────────────────────────────────────────────

    def call(self, prompt: str) -> LLMResponse:
        """Синхронный вызов LLM. Возвращает LLMResponse."""
        self._validate_prompt(prompt)

        try:
            response = self._client.chat.completions.create(
                **self._build_request_kwargs(prompt),
            )
            return self._parse_response(response)

        except Exception as exc:
            raise self._map_exception(exc) from exc

    def stream(self, prompt: str) -> Iterator[str]:
        """Синхронная потоковая генерация."""
        self._validate_prompt(prompt)

        try:
            response_stream = self._client.chat.completions.create(
                **self._build_request_kwargs(prompt),
                stream=True,
            )

            for chunk in response_stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content

        except Exception as exc:
            raise self._map_exception(exc) from exc

    # ─────────────────────────────────────────────
    # Асинхронные методы
    # ─────────────────────────────────────────────

    async def acall(self, prompt: str) -> LLMResponse:
        """Асинхронный вызов LLM. Возвращает LLMResponse."""
        self._validate_prompt(prompt)

        try:
            response = await self._async_client.chat.completions.create(
                **self._build_request_kwargs(prompt),
            )
            return self._parse_response(response)

        except Exception as exc:
            raise self._map_exception(exc) from exc

    async def astream(self, prompt: str) -> AsyncIterator[str]:
        """Асинхронная потоковая генерация."""
        self._validate_prompt(prompt)

        try:
            response_stream = await self._async_client.chat.completions.create(
                **self._build_request_kwargs(prompt),
                stream=True,
            )

            async for chunk in response_stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content

        except Exception as exc:
            raise self._map_exception(exc) from exc

    # ─────────────────────────────────────────────
    # Приватные методы
    # ─────────────────────────────────────────────

    def _build_client_kwargs(self) -> dict:
        """Kwargs для инициализации клиентов. Использует ApiConfig."""
        kwargs: dict = {
            "api_key": self._api_config.api_key,
            "timeout": self._api_config.timeout_seconds,
        }
        if self._api_config.base_url:
            kwargs["base_url"] = self._api_config.base_url
        return kwargs

    def _build_request_kwargs(self, prompt: str) -> dict:
        """Kwargs для каждого запроса."""
        return {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        """Валидация промпта."""
        if not prompt or not prompt.strip():
            raise LLMInvalidRequestError("Промпт не может быть пустым")

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        """Парсит ответ OpenAI в LLMResponse."""
        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            text=choice.message.content or "",
            tokens_used=usage.total_tokens if usage else 0,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=response.model or "",
            finish_reason=choice.finish_reason or "stop",
        )

    @staticmethod
    def _map_exception(exc: Exception) -> LLMEngineError:
        """Маппинг openai exceptions → наша иерархия."""
        if not HAS_OPENAI:
            return LLMEngineError(str(exc))

        mapping: dict[type, type] = {
            openai.AuthenticationError: LLMAuthenticationError,
            openai.RateLimitError: LLMRateLimitError,
            openai.BadRequestError: LLMInvalidRequestError,
            openai.APIConnectionError: LLMConnectionError,
            openai.APITimeoutError: LLMTimeoutError,
        }

        for openai_exc_type, our_exc_type in mapping.items():
            if isinstance(exc, openai_exc_type):
                return our_exc_type(str(exc))

        if isinstance(exc, openai.APIError):
            return LLMEngineError(f"API error: {exc}")

        return LLMEngineError(f"Unexpected error: {exc}")