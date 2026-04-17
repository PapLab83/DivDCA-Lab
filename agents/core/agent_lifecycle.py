"""
AgentLifecycle — управление жизненным циклом выполнения агента.

Выделен из BaseAgent как самостоятельный компонент (декомпозиция).

Отвечает за:
- замер времени выполнения
- добавление метаданных к AgentResult (duration_ms, agent_class)
- логирование результата выполнения
- вызов хуков setup/cleanup

Не отвечает за:
- бизнес-логику агента (это _execute_internal)
- парсинг ответов LLM (это ResponseParser)
- маппинг исключений (это ErrorMapper)

Использование:
    lifecycle = AgentLifecycle(agent_class_name="EventGenerationAgent")
    start = lifecycle.start()
    ...
    result = lifecycle.finalize(context, start, raw_result)
"""
import logging
import time
from dataclasses import replace
from typing import Any, Callable, Dict, Optional

from agents.core.base_agent import AgentContext, AgentResult

logger = logging.getLogger(__name__)


class AgentLifecycle:
    """
    Управляет жизненным циклом одного выполнения агента.

    Инкапсулирует:
    - старт таймера
    - финализацию результата (duration, metadata)
    - логирование

    Один экземпляр создаётся на класс агента (не на вызов).
    Методы start/finalize вызываются на каждый execute().
    """

    def __init__(self, agent_class_name: str) -> None:
        """
        Args:
            agent_class_name: имя класса агента для метаданных и логов
        """
        self._agent_class_name = agent_class_name

    # ── Таймер ────────────────────────────────────────────────────

    def start(self) -> float:
        """
        Запускает таймер выполнения.

        Returns:
            Монотонное время старта (передать в finalize)
        """
        return time.monotonic()

    # ── Хуки ──────────────────────────────────────────────────────

    def run_setup(
        self,
        context: AgentContext,
        setup_fn: Callable[[AgentContext], None],
    ) -> None:
        """
        Вызывает хук setup с логированием.

        Args:
            context: контекст выполнения
            setup_fn: функция setup из агента
        """
        logger.info(
            "Запуск агента %s (task=%s, agent_id=%s)",
            self._agent_class_name, context.task, context.agent_id,
        )
        setup_fn(context)

    def run_cleanup(
        self,
        context: AgentContext,
        cleanup_fn: Callable[[AgentContext], None],
    ) -> None:
        """
        Вызывает хук cleanup.

        Args:
            context: контекст выполнения
            cleanup_fn: функция cleanup из агента
        """
        cleanup_fn(context)

    # ── Финализация ───────────────────────────────────────────────

    def finalize(
        self,
        context: AgentContext,
        start_time: float,
        result: AgentResult,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        """
        Финализирует результат: добавляет duration_ms и метаданные.

        Args:
            context: контекст выполнения (для cleanup)
            start_time: время старта из start()
            result: сырой AgentResult из _execute_internal или _handle_error
            extra_metadata: дополнительные метаданные для слияния

        Returns:
            Новый AgentResult с заполненными duration_ms и metadata
        """
        duration_ms = int((time.monotonic() - start_time) * 1000)

        merged_metadata = {
            **result.metadata,
            "agent_class": self._agent_class_name,
            **(extra_metadata or {}),
        }

        finalized = replace(
            result,
            duration_ms=duration_ms,
            metadata=merged_metadata,
        )

        self._log_result(finalized)
        return finalized

    # ── Логирование ───────────────────────────────────────────────

    def _log_result(self, result: AgentResult) -> None:
        """Логирует итог выполнения агента."""
        duration = result.duration_ms if result.duration_ms is not None else -1
        if result.success:
            logger.info(
                "Агент %s успешно выполнен за %dмс",
                self._agent_class_name, duration,
            )
        else:
            logger.warning(
                "Агент %s завершился с ошибкой за %dмс: %s",
                self._agent_class_name, duration, result.error,
            )

    def __repr__(self) -> str:
        return f"AgentLifecycle(agent={self._agent_class_name!r})"