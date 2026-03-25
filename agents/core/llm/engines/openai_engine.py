"""
OpenAI LLM engine — синхронный и асинхронный вызов OpenAI API.
"""

import logging
from typing import AsyncIterator, Iterator, Optional


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


class OpenAIEngine(BaseLLMEngine):
    """
    Engine для работы с OpenAI API (GPT-4o, GPT-4, GPT-3.5 и т.д.).

    Поддерживает:
        - синхронные и асинхронные вызовы
        - потоковую генерацию (streaming)
        - автоматический retry и обработку ошибок

    Пример::

        config = LLMConfig(model="gpt-4o", api_key="sk-...")
        engine = OpenAIEngine(config)

        # Синхронно
        response = engine.call("Привет!")

        # Асинхронно
        response = await engine.acall("Привет!")

        # Стриминг
        for chunk in engine.stream("Расскажи историю"):
            print(chunk, end="")
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
            "OpenAIEngine создан: model=%s, base_url=%s",
            config.model,
            config.base_url or "default",
        )

    # ─────────────────────────────────────────────
    # Синхронные методы
    # ─────────────────────────────────────────────

    def call(self, prompt: str) -> LLMResponse:
        """
        Синхронный вызов OpenAI Chat Completions API.

        Args:
            prompt: текст промпта

        Returns:
            LLMResponse с текстом и метаданными
        """
        self._validate_prompt(prompt)

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                **self.config.extra,
            )
            return self._parse_response(response)

        except Exception as exc:
            raise self._map_exception(exc) from exc

    def stream(self, prompt: str) -> Iterator[str]:
        """
        Синхронная потоковая генерация.

        Args:
            prompt: текст промпта

        Yields:
            Части текста по мере генерации
        """
        self._validate_prompt(prompt)

        try:
            response_stream = self._client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True,
                **self.config.extra,
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
        """
        Асинхронный вызов OpenAI Chat Completions API.

        Args:
            prompt: текст промпта

        Returns:
            LLMResponse с текстом и метаданными
        """
        self._validate_prompt(prompt)

        try:
            response = await self._async_client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                **self.config.extra,
            )
            return self._parse_response(response)

        except Exception as exc:
            raise self._map_exception(exc) from exc

    async def astream(self, prompt: str) -> AsyncIterator[str]:
        """
        Асинхронная потоковая генерация.

        Args:
            prompt: текст промпта

        Yields:
            Части текста по мере генерации
        """
        self._validate_prompt(prompt)

        try:
            response_stream = await self._async_client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True,
                **self.config.extra,
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
        """Собирает kwargs для инициализации клиентов OpenAI."""
        kwargs: dict = {
            "api_key": self.config.api_key,
            "timeout": self.config.timeout,
            "max_retries": self.config.max_retries,
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        return kwargs

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        """Валидация входного промпта."""
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
        """
        Маппинг исключений openai → наши LLMEngineError.
        Если openai не установлен — оборачиваем как есть.
        """
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
            return LLMEngineError(f"OpenAI API error: {exc}")

        return LLMEngineError(f"Unexpected error: {exc}")