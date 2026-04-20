# mas/price_drivers_collection/pipeline.py
"""
Pipeline для обработки одного тикера за период.
Вызывает агента для каждого года, собирает результаты.
"""

__all__ = [
    "PipelineConfig",
    "process_ticker",
]

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agents.core.base_agent import AgentContext, AgentResult, BaseAgent
from agents.core.types import make_metadata
from agents.core.profiles import UserProfile
from agents.core.profiles.profile_validator import ProfileValidator
from mas.price_drivers_collection.cancellable_task import CancellableTask

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """
    Настройки pipeline обработки тикеров.

    Attributes:
        call_timeout_seconds: максимальное время ожидания одного вызова агента.
        rate_limit_delay_seconds: задержка между вызовами агента.
        rate_limit_backoff_on_error: множитель задержки при ошибке.
        max_workers: количество потоков в ThreadPoolExecutor.
    """
    call_timeout_seconds: float = 30.0
    rate_limit_delay_seconds: float = 0.0
    rate_limit_backoff_on_error: float = 2.0
    max_workers: int = 1

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """
        Создаёт PipelineConfig из переменных окружения.

        Приоритет: ENV vars → defaults в коде.

        Env vars:
            PIPELINE_CALL_TIMEOUT:       таймаут одного вызова агента (сек), default: 30.0
            PIPELINE_RATE_LIMIT_DELAY:   задержка между вызовами (сек), default: 0.0
            PIPELINE_RATE_LIMIT_BACKOFF: множитель задержки при ошибке, default: 2.0
            PIPELINE_MAX_WORKERS:        потоков в ThreadPoolExecutor, default: 1
        """
        import os

        defaults = cls()
        return cls(
            call_timeout_seconds=float(
                os.getenv("PIPELINE_CALL_TIMEOUT", defaults.call_timeout_seconds)
            ),
            rate_limit_delay_seconds=float(
                os.getenv("PIPELINE_RATE_LIMIT_DELAY", defaults.rate_limit_delay_seconds)
            ),
            rate_limit_backoff_on_error=float(
                os.getenv("PIPELINE_RATE_LIMIT_BACKOFF", defaults.rate_limit_backoff_on_error)
            ),
            max_workers=int(
                os.getenv("PIPELINE_MAX_WORKERS", defaults.max_workers)
            ),
        )


def _call_agent_with_timeout(
    agent: BaseAgent,
    context: AgentContext,
    timeout_seconds: float,
) -> AgentResult:
    """
    Вызывает агента с ограничением по времени через CancellableTask.

    Использует daemon-поток вместо ThreadPoolExecutor:
        - future.cancel() не останавливает запущенный поток (Python limitation)
        - daemon=True гарантирует что зависший поток не блокирует завершение процесса
        - join(timeout) корректно обрабатывает истечение времени

    Args:
        agent: экземпляр агента
        context: контекст вызова
        timeout_seconds: максимальное время ожидания

    Returns:
        AgentResult — успех или ошибка таймаута
    """
    task = CancellableTask(fn=agent.execute, args=(context,))
    try:
        return task.run(timeout_seconds=timeout_seconds)
    except TimeoutError as e:
        logger.error(
            "Timeout (%ss) для агента %s/%s",
            timeout_seconds,
            context.metadata.get("ticker", "?"),
            context.metadata.get("year", "?"),
        )
        return AgentResult(
            success=False,
            error=(
                f"TimeoutError: агент не ответил за {timeout_seconds}с. "
                f"Проверьте доступность LLM API или увеличьте PIPELINE_CALL_TIMEOUT."
            ),
        )


def process_ticker(
    agent: BaseAgent,
    ticker: str,
    records: List[Dict[str, Any]],
    pipeline_config: Optional[PipelineConfig] = None,
    profile: Optional[UserProfile] = None,
) -> List[Dict[str, Any]]:
    """
    Обрабатывает один тикер за период.

    При max_workers=1 (default) — sequential обработка без накладных расходов
    ThreadPoolExecutor. При max_workers>1 — параллельная обработка записей
    через отдельные потоки.

    Args:
        agent: готовый экземпляр агента.
        ticker: символ тикера.
        records: список записей [{year, price, dividend, yoy_change}, ...]
        pipeline_config: настройки rate limiting и timeout.
        profile: UserProfile (опционально).

    Returns:
        Список результатов по каждому году.
    """
    if not records:
        return []

    cfg = pipeline_config or PipelineConfig.from_env()

    # Выбор стратегии обработки
    if cfg.max_workers <= 1:
        results = _process_sequential(agent, ticker, records, cfg)
    else:
        results = _process_parallel(agent, ticker, records, cfg)

    # Фильтрация по профилю если передан
    if profile is not None:
        validator = ProfileValidator(profile)
        passed, rejected = validator.split_results(results)
        if rejected:
            logger.info(
                "ProfileValidator: отклонено %d/%d записей для %s",
                len(rejected), len(results), ticker,
            )
        return passed

    return results


def _process_sequential(
    agent: BaseAgent,
    ticker: str,
    records: List[Dict[str, Any]],
    cfg: PipelineConfig,
) -> List[Dict[str, Any]]:
    """
    Sequential обработка записей без ThreadPoolExecutor.

    Используется при max_workers=1 (default).
    Нет overhead создания пула потоков.
    """
    results = []
    current_delay = cfg.rate_limit_delay_seconds

    for i, record in enumerate(records):
        year = record["year"]
        logger.info("Processing %s / %d (sequential)", ticker, year)

        if i > 0 and current_delay > 0:
            logger.debug(
                "Rate limit delay: %.2fs перед %s/%d",
                current_delay, ticker, year,
            )
            import time
            time.sleep(current_delay)

        context = _build_context(ticker, record)
        result = _call_agent_with_timeout(
            agent=agent,
            context=context,
            timeout_seconds=cfg.call_timeout_seconds,
        )

        entry = _build_result_entry(ticker, record, result)
        results.append(entry)
        current_delay = _update_delay(cfg, result, current_delay, ticker, year)

    return results


def _process_parallel(
    agent: BaseAgent,
    ticker: str,
    records: List[Dict[str, Any]],
    cfg: PipelineConfig,
) -> List[Dict[str, Any]]:
    """
    Параллельная обработка записей через ThreadPoolExecutor.

    Используется при max_workers>1.
    Rate limiting в параллельном режиме не применяется —
    управление задержками между потоками требует отдельной реализации.

    Note:
        Порядок результатов соответствует порядку records (zip).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = [None] * len(records)  # сохраняем порядок

    with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
        future_to_index = {
            executor.submit(
                _call_agent_with_timeout,
                agent,
                _build_context(ticker, record),
                cfg.call_timeout_seconds,
            ): i
            for i, record in enumerate(records)
        }

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            record = records[idx]
            try:
                result = future.result()
            except Exception as e:
                logger.error("Unexpected error in parallel worker: %s", e)
                result = AgentResult(success=False, error=str(e))

            results[idx] = _build_result_entry(ticker, record, result)
            _log_result(ticker, record["year"], result)

    return results


def _build_context(ticker: str, record: Dict[str, Any]) -> AgentContext:
    """Строит AgentContext из записи тикера."""
    return AgentContext(
        agent_id=f"{ticker}-{record['year']}",
        task="event_generation",
        metadata=make_metadata({
            "ticker": ticker,
            "year": record["year"],
            "price": record["price"],
            "dividend": record["dividend"],
            "yoy_change": record["yoy_change"],
        }),
    )


def _build_result_entry(
    ticker: str,
    record: Dict[str, Any],
    result: AgentResult,
) -> Dict[str, Any]:
    """Строит dict результата из AgentResult."""
    return {
        "ticker": ticker,
        "year": record["year"],
        "price": record["price"],
        "dividend": record["dividend"],
        "success": result.success,
        "data": result.data,
        "error": result.error,
        "duration_ms": result.duration_ms,
        "prompt_version": result.prompt_version,
    }


def _update_delay(
    cfg: PipelineConfig,
    result: AgentResult,
    current_delay: float,
    ticker: str,
    year: int,
) -> float:
    """Обновляет задержку rate limiting после результата."""
    if result.success:
        logger.info(
            "  ✓ %s/%d: %s (confidence=%.2f, %dms)",
            ticker, year,
            result.data.get("reason_short", "?") if result.data else "?",
            result.data.get("confidence", 0) if result.data else 0,
            result.duration_ms or 0,
        )
        return cfg.rate_limit_delay_seconds  # сброс к базовому

    if cfg.rate_limit_delay_seconds > 0:
        new_delay = min(
            current_delay * cfg.rate_limit_backoff_on_error,
            60.0,
        )
        logger.warning(
            "  ✗ %s/%d: %s (следующая задержка: %.2fs)",
            ticker, year, result.error, new_delay,
        )
        return new_delay

    logger.warning("  ✗ %s/%d: %s", ticker, year, result.error)
    return current_delay


def _log_result(ticker: str, year: int, result: AgentResult) -> None:
    """Логирует результат (используется в параллельном режиме)."""
    if result.success:
        logger.info(
            "  ✓ %s/%d: %s (confidence=%.2f, %dms)",
            ticker, year,
            result.data.get("reason_short", "?") if result.data else "?",
            result.data.get("confidence", 0) if result.data else 0,
            result.duration_ms or 0,
        )
    else:
        logger.warning("  ✗ %s/%d: %s", ticker, year, result.error)