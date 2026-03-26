"""
Исключения LLM-слоя.
Единственное место определения — все остальные модули импортируют отсюда.
"""


class LLMEngineError(Exception):
    """Базовая ошибка LLM engine."""


class LLMTransientError(LLMEngineError):
    """Временная ошибка, при которой имеет смысл retry (таймаут, rate limit, 5xx)."""


class LLMConnectionError(LLMTransientError):
    """Ошибка соединения с провайдером."""


class LLMRateLimitError(LLMTransientError):
    """Превышен лимит запросов."""


class LLMTimeoutError(LLMTransientError):
    """Таймаут запроса."""


class LLMAuthenticationError(LLMEngineError):
    """Ошибка аутентификации (невалидный API-ключ)."""


class LLMInvalidRequestError(LLMEngineError):
    """Некорректный запрос (prompt слишком длинный и т.д.)."""


class LLMParseError(LLMEngineError):
    """Ошибка парсинга ответа от LLM (невалидный JSON и т.д.)."""

    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


__all__ = [
    "LLMEngineError",
    "LLMTransientError",
    "LLMConnectionError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMAuthenticationError",
    "LLMInvalidRequestError",
    "LLMParseError",
]