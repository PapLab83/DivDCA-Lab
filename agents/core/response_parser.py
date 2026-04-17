"""
ResponseParser — парсинг и валидация ответов LLM.

Выделен из BaseAgent как самостоятельный компонент (декомпозиция).

Отвечает за:
- извлечение JSON из raw-ответа LLM (включая markdown-блоки)
- валидацию структуры распарсенного результата
- генерацию LLMParseError с сохранением raw_response для отладки

Не отвечает за:
- вызов LLM (это LLMAdapter)
- жизненный цикл агента (это AgentLifecycle)
- маппинг исключений (это ErrorMapper)

Использование:
    parser = ResponseParser(required_fields={"reason_short", "confidence"})
    data = parser.parse(raw_response)   # Dict[str, Any] или LLMParseError
"""
import json
import logging
import re
from typing import Any, Callable, Dict, Optional, Set

from agents.core.llm.exceptions import LLMParseError

logger = logging.getLogger(__name__)


class ResponseParser:
    """
    Парсер ответов LLM.

    Поддерживает:
    - чистый JSON
    - JSON в markdown-блоках (```json ... ```)
    - кастомную валидацию через validator callable

    Args:
        required_fields: набор обязательных ключей в результате.
            Если None — валидация структуры не выполняется (только JSON-парсинг).
        validator: дополнительная функция валидации result → bool.
            Вызывается после проверки required_fields.
            Если возвращает False — бросает LLMParseError.
    """

    def __init__(
        self,
        required_fields: Optional[Set[str]] = None,
        validator: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> None:
        self._required_fields = required_fields or set()
        self._validator = validator

    # ── Публичный интерфейс ───────────────────────────────────────

    def parse(self, response: str) -> Dict[str, Any]:
        """
        Парсит raw-ответ LLM в словарь.

        Шаги:
            1. Извлечение JSON из markdown-блока (если есть)
            2. json.loads
            3. Проверка required_fields
            4. Вызов кастомного validator (если задан)

        Args:
            response: сырой текст ответа от LLM

        Returns:
            Распарсенный словарь

        Raises:
            LLMParseError: если JSON невалидный или валидация не пройдена
        """
        cleaned = self._extract_json(response)
        parsed = self._loads(cleaned, raw_response=response)
        self._validate(parsed, raw_response=response)
        return parsed

    def validate_only(self, data: Dict[str, Any]) -> bool:
        """
        Только валидация уже распарсенного словаря.
        Не бросает исключений — возвращает bool.
        Полезно для мягкой проверки без прерывания потока.
        """
        if self._required_fields and not self._required_fields.issubset(data.keys()):
            return False
        if self._validator is not None:
            return self._validator(data)
        return True

    # ── Приватные методы ──────────────────────────────────────────

    @staticmethod
    def _extract_json(response: str) -> str:
        """
        Извлекает JSON из markdown-блока или возвращает строку как есть.

        Поддерживает:
            ```json { ... } ```
            ``` { ... } ```
        """
        cleaned = response.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            return match.group(1)
        return cleaned

    @staticmethod
    def _loads(text: str, raw_response: str) -> Dict[str, Any]:
        """json.loads с конвертацией ошибки в LLMParseError."""
        try:
            parsed: Dict[str, Any] = json.loads(text.strip())
            return parsed
        except json.JSONDecodeError as e:
            logger.error("Ошибка парсинга JSON: %s", e)
            logger.debug("Ответ LLM: %s", raw_response)
            raise LLMParseError(
                message=f"Ошибка парсинга JSON: {e}",
                raw_response=raw_response,
            ) from e

    def _validate(self, parsed: Dict[str, Any], raw_response: str) -> None:
        """
        Валидирует распарсенный словарь.
        Бросает LLMParseError если валидация не пройдена.
        """
        if self._required_fields:
            missing = self._required_fields - set(parsed.keys())
            if missing:
                raise LLMParseError(
                    message=f"Отсутствуют обязательные поля: {missing}",
                    raw_response=raw_response,
                )

        if self._validator is not None and not self._validator(parsed):
            raise LLMParseError(
                message="Результат не прошёл кастомную валидацию",
                raw_response=raw_response,
            )

    def __repr__(self) -> str:
        return (
            f"ResponseParser("
            f"required_fields={self._required_fields!r}, "
            f"has_validator={self._validator is not None})"
        )