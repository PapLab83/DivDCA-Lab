"""
ErrorMapper — маппинг исключений в AgentResult.

Выделен из BaseAgent как самостоятельный компонент (декомпозиция).

Отвечает за:
- конвертацию любого Exception в AgentResult(success=False)
- защиту от исключений внутри самого обработчика ошибок
- расширяемый маппинг по типу исключения

Не отвечает за:
- парсинг ответов (это ResponseParser)
- жизненный цикл (это AgentLifecycle)
- бизнес-логику агента

Использование:
    mapper = ErrorMapper()
    result = mapper.handle(exception, agent_class_name="MyAgent")

    # Расширенный маппинг:
    mapper = ErrorMapper(custom_handlers={
        ValueError: lambda e: AgentResult(success=False, error=f"Bad input: {e}"),
    })
"""
import logging
from typing import Callable, Dict, Optional, Type

from agents.core.base_agent import AgentResult

logger = logging.getLogger(__name__)

# Тип обработчика: принимает исключение, возвращает AgentResult
ErrorHandler = Callable[[Exception], AgentResult]


class ErrorMapper:
    """
    Маппинг исключений в AgentResult.

    Поддерживает:
    - дефолтный маппинг (любой Exception → AgentResult с error-строкой)
    - кастомные обработчики по типу исключения
    - защиту от исключений внутри обработчика (critical fallback)

    Args:
        custom_handlers: словарь {ExceptionType: handler_fn}.
            Обработчики проверяются через isinstance в порядке добавления.
            Если совпадений нет — используется дефолтный обработчик.
    """

    def __init__(
        self,
        custom_handlers: Optional[Dict[Type[Exception], ErrorHandler]] = None,
    ) -> None:
        self._custom_handlers: Dict[Type[Exception], ErrorHandler] = (
            custom_handlers or {}
        )

    # ── Публичный интерфейс ───────────────────────────────────────

    def handle(
        self,
        error: Exception,
        agent_class_name: str = "UnknownAgent",
    ) -> AgentResult:
        """
        Конвертирует исключение в AgentResult.

        Порядок:
            1. Ищет кастомный обработчик по isinstance
            2. Если не найден — дефолтный маппинг
            3. Если обработчик сам бросил исключение — critical fallback

        Args:
            error: пойманное исключение
            agent_class_name: имя агента для метаданных и логов

        Returns:
            AgentResult(success=False, error=..., metadata={agent_class: ...})
        """
        try:
            result = self._dispatch(error)
            # Гарантируем agent_class в metadata
            metadata = {**result.metadata, "agent_class": agent_class_name}
            from dataclasses import replace
            return replace(result, metadata=metadata)
        except Exception as inner:
            logger.critical(
                "ErrorMapper: исключение внутри обработчика ошибки: %s",
                inner,
                exc_info=True,
            )
            return AgentResult(
                success=False,
                error=f"Critical: {inner.__class__.__name__}: {inner}",
                metadata={"agent_class": agent_class_name},
            )

    def register(
        self,
        exc_type: Type[Exception],
        handler: ErrorHandler,
    ) -> None:
        """
        Регистрирует кастомный обработчик для типа исключения.

        Args:
            exc_type: тип исключения (проверяется через isinstance)
            handler: функция (Exception) → AgentResult
        """
        self._custom_handlers[exc_type] = handler
        logger.debug("ErrorMapper: зарегистрирован обработчик для %s", exc_type.__name__)

    # ── Приватные методы ──────────────────────────────────────────

    def _dispatch(self, error: Exception) -> AgentResult:
        """Ищет подходящий обработчик и вызывает его."""
        for exc_type, handler in self._custom_handlers.items():
            if isinstance(error, exc_type):
                logger.debug(
                    "ErrorMapper: кастомный обработчик для %s",
                    type(error).__name__,
                )
                return handler(error)

        return self._default_handler(error)

    @staticmethod
    def _default_handler(error: Exception) -> AgentResult:
        """Дефолтный маппинг: любое исключение → AgentResult с error-строкой."""
        logger.error(
            "Ошибка агента: %s: %s",
            error.__class__.__name__, error,
            exc_info=True,
        )
        return AgentResult(
            success=False,
            error=f"{error.__class__.__name__}: {error}",
        )

    def __repr__(self) -> str:
        handlers = [t.__name__ for t in self._custom_handlers]
        return f"ErrorMapper(custom_handlers={handlers!r})"