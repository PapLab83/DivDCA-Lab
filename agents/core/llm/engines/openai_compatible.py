"""
Универсальный OpenAI-совместимый LLM engine.

Работает с любым провайдером через GPT-тунель или напрямую:
OpenAI, Claude, Gemini, Mistral, LLaMA и т.д.
"""

import logging
from typing import AsyncIterator, Iterator

try:
    import openai
    from openai import AsyncOpenAI, OpenAI

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from agents.core.llm.engines.base_engine import (
    BaseLLMEngine,
    LLMAuthenticationError,
    LLMConfig,
    LLMConnectionError,
    LLMEngineError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleEngine(BaseLLMEngine):
    """
    Универсальный engine для любого OpenAI-совместимого API.

    Работает с:
        - OpenAI напрямую (base_url не нужен)
        - GPT-тунель → Claude, Gemini, Mistral и т.д. (base_url обязателен)

    Пример::

        # OpenAI напрямую
        config = LLMConfig(model="gpt-4o", api_key="sk-...")
        engine = OpenAICompatibleEngine(config)

        # Claude через тунель
        config = LLMConfig(
            model="claude-sonnet-4-20250514",
            api_key="tunnel-key",
            base_url="https://gpt-tunnel.example.com/v1",
        )
        engine = OpenAICompatibleEngine(config)

        # Gemini через тунель
        config = LLMConfig(
            model="gemini-2.0-flash",
            api_key="tunnel-key",
            base_url="https://gpt-tunnel.example.com/v1",
        )
        engine = OpenAICompatibleEngine(config)
    """

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)

        if not HAS_OPENAI:
            raise LLMEngineError(
                "Пакет 'openai' не установлен. Установите: pip install openai"
            )

        client_kwargs = self._build_client_kwargs()

        self._client: OpenAI = OpenAI(**client_kwargs)
        self._async_client: AsyncOpenAI = AsyncOpenAI(**client_kwargs)

        logger.debug(
            "OpenAICompatibleEngine создан: model=%s, base_url=%s",
            config.model,
            config.base_url or "default",
        )

    # ─────────────────────────────────────────────
    # Синхронные методы
    # ─────────────────────────────────────────────

    def call(self, prompt: str) -> LLMResponse:
        """Синхронный вызов LLM."""
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
        """Асинхронный вызов LLM."""
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
        """Kwargs для инициализации клиентов."""
        kwargs: dict = {
            "api_key": self.config.api_key,
            "timeout": self.config.timeout,
            "max_retries": self.config.max_retries,
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        return kwargs

    def _build_request_kwargs(self, prompt: str) -> dict:
        """Kwargs для каждого запроса (DRY для call/stream/acall/astream)."""
        return {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            **self.config.extra,
        }

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        """Валидация промпта."""
        if not prompt or not prompt.strip():
            raise LLMInvalidRequestError("Промпт не может быть пустым")

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        """Парсит ответ в LLMResponse."""
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
        """Маппинг openai exceptions → LLMEngineError."""
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