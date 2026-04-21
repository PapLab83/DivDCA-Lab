# mas/price_drivers_collection/pipeline.py
"""
Pipeline для обработки одного тикера за период.
Вызывает агента для каждого года, собирает результаты.

Известные ограничения:
    Parallel режим (max_workers > 1):
        - rate_limit_delay_seconds игнорируется
        - rate_limit_backoff_on_error игнорируется
        - рекомендуется только при LLM_PROVIDER=mock или провайдерах без rate limits
        - порядок результатов сохраняется (по индексу записи)
    Планируемое решение: async pipeline (см. TODO в cancellable_task.py)
"""

__all__ = [
    "PipelineConfig",
    "process_ticker",
]

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            ⚠️  Применяется только в sequential режиме (max_workers=1).
            В parallel режиме игнорируется — управление задержками между
            потоками требует отдельной реализации (см. TODO в cancellable_task.py).
        rate_limit_backoff_on_error: множитель задержки при ошибке.
            ⚠️  Применяется только в sequential режиме (max_workers=1).
            В parallel режиме игнорируется.
        max_workers: количество потоков в ThreadPoolExecutor.
            1 (default) — sequential обработка без overhead пула потоков.
            >1 — parallel обработка. Rate limiting не применяется.
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
                                         ⚠️  только для sequential режима
            PIPELINE_RATE_LIMIT_BACKOFF: множитель задержки при ошибке, default: 2.0
                                         ⚠️  только для sequential режима
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

    ⚠️  Parallel режим (max_workers>1): rate limiting не применяется.
        Используйте только с провайдерами без rate limits (mock, выделенный endpoint).

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


def _execute_single_record(
    agent: BaseAgent,
    ticker: str,
    record: Dict[str, Any],
    cfg: PipelineConfig,
) -> Dict[str, Any]:
    """
    Выполняет обработку одной записи с гарантированным результатом.

    Единая точка вызова агента для sequential и parallel режимов.
    Гарантия: никогда не бросает исключение — всегда возвращает Dict.
    При любой ошибке (включая ошибку в _build_result_entry) возвращает
    запись с success=False и описанием ошибки.

    Args:
        agent: экземпляр агента
        ticker: символ тикера
        record: одна запись {year, price, dividend, yoy_change}
        cfg: конфигурация pipeline

    Returns:
        Dict с полями: ticker, year, price, dividend, success, data, error,
        duration_ms, prompt_version. Никогда не None.
    """
    try:
        context = _build_context(ticker, record)
        result = _call_agent_with_timeout(
            agent=agent,
            context=context,
            timeout_seconds=cfg.call_timeout_seconds,
        )
        return _build_result_entry(ticker, record, result)
    except Exception as e:
        # Защита от неожиданных ошибок в _build_context или _build_result_entry.
        # В норме не должно происходить — record валидируется на входе в pipeline.
        logger.error(
            "Неожиданная ошибка при обработке %s/%s: %s",
            ticker,
            record.get("year", "?"),
            e,
            exc_info=True,
        )
        return _build_result_entry(
            ticker,
            record,
            AgentResult(
                success=False,
                error=f"Unexpected pipeline error: {e.__class__.__name__}: {e}",
            ),
        )


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
    Rate limiting (delay + backoff) применяется между вызовами.
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
            time.sleep(current_delay)

        entry = _execute_single_record(agent, ticker, record, cfg)
        results.append(entry)

        # Обновляем задержку на основе результата (backoff при ошибке)
        current_delay = _update_delay(cfg, entry, current_delay, ticker, year)

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

    ⚠️  Rate limiting не применяется в parallel режиме.
        rate_limit_delay_seconds и rate_limit_backoff_on_error игнорируются.
        Управление задержками между потоками требует отдельной реализации.
        Используйте только с провайдерами без rate limits.

    Note:
        Порядок результатов соответствует порядку records (по индексу).
        Гарантия: results[i] всегда соответствует records[i], никогда не None.
    """
    # Предупреждение если rate limiting настроен но будет проигнорирован
    if cfg.rate_limit_delay_seconds > 0:
        logger.warning(
            "PipelineConfig.rate_limit_delay_seconds=%.2f будет проигнорирован "
            "в parallel режиме (max_workers=%d). "
            "Rate limiting не поддерживается в parallel режиме. "
            "Используйте max_workers=1 если провайдер имеет rate limits.",
            cfg.rate_limit_delay_seconds,
            cfg.max_workers,
        )

    if cfg.rate_limit_backoff_on_error != PipelineConfig.rate_limit_backoff_on_error:
        logger.warning(
            "PipelineConfig.rate_limit_backoff_on_error=%.2f будет проигнорирован "
            "в parallel режиме (max_workers=%d). "
            "Backoff не поддерживается в parallel режиме.",
            cfg.rate_limit_backoff_on_error,
            cfg.max_workers,
        )

    # Инициализируем список с sentinel-значениями для детектирования пропусков.
    # После заполнения все элементы должны быть Dict — не None.
    results: List[Optional[Dict[str, Any]]] = [None] * len(records)

    with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
        future_to_index = {
            executor.submit(
                _execute_single_record,
                agent,
                ticker,
                record,
                cfg,
            ): i
            for i, record in enumerate(records)
        }

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            record = records[idx]
            try:
                # _execute_single_record гарантирует возврат Dict, не бросает исключений.
                # future.result() может бросить только если executor сам упал (редко).
                result_entry = future.result()
            except Exception as e:
                # Защита от неожиданных ошибок executor (не от ошибок агента).
                logger.error(
                    "Неожиданная ошибка executor для %s/%s: %s",
                    ticker, record.get("year", "?"), e,
                    exc_info=True,
                )
                result_entry = _build_result_entry(
                    ticker,
                    record,
                    AgentResult(
                        success=False,
                        error=f"Executor error: {e.__class__.__name__}: {e}",
                    ),
                )

            results[idx] = result_entry
            _log_result(ticker, record["year"], result_entry)

    # Финальная проверка: убеждаемся что нет None (защита от багов в логике выше).
    # В норме не должно срабатывать — каждый индекс заполняется в цикле выше.
    final_results = []
    for i, entry in enumerate(results):
        if entry is None:
            logger.error(
                "BUG: results[%d] is None для %s/%s — запись пропущена. "
                "Это не должно происходить. Проверьте логику _process_parallel.",
                i, ticker, records[i].get("year", "?"),
            )
            # Создаём запись об ошибке чтобы не потерять запись из статистики
            final_results.append(_build_result_entry(
                ticker,
                records[i],
                AgentResult(
                    success=False,
                    error="BUG: result was None after parallel processing",
                ),
            ))
        else:
            final_results.append(entry)

    return final_results


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
    entry: Dict[str, Any],
    current_delay: float,
    ticker: str,
    year: int,
) -> float:
    """
    Обновляет задержку rate limiting после результата.

    Принимает entry (Dict) вместо AgentResult — унифицировано с _execute_single_record.
    Используется только в sequential режиме.
    """
    success = entry.get("success", False)
    error = entry.get("error")
    data = entry.get("data")

    if success:
        logger.info(
            "  ✓ %s/%d: %s (confidence=%.2f, %dms)",
            ticker, year,
            data.get("reason_short", "?") if data else "?",
            data.get("confidence", 0) if data else 0,
            entry.get("duration_ms") or 0,
        )
        return cfg.rate_limit_delay_seconds  # сброс к базовому

    if cfg.rate_limit_delay_seconds > 0:
        new_delay = min(
            current_delay * cfg.rate_limit_backoff_on_error,
            60.0,
        )
        logger.warning(
            "  ✗ %s/%d: %s (следующая задержка: %.2fs)",
            ticker, year, error, new_delay,
        )
        return new_delay

    logger.warning("  ✗ %s/%d: %s", ticker, year, error)
    return current_delay


def _log_result(ticker: str, year: int, entry: Dict[str, Any]) -> None:
    """
    Логирует результат (используется в parallel режиме).

    Принимает entry (Dict) — унифицировано с _update_delay.
    """
    success = entry.get("success", False)
    data = entry.get("data")
    error = entry.get("error")

    if success:
        logger.info(
            "  ✓ %s/%d: %s (confidence=%.2f, %dms)",
            ticker, year,
            data.get("reason_short", "?") if data else "?",
            data.get("confidence", 0) if data else 0,
            entry.get("duration_ms") or 0,
        )
    else:
        logger.warning("  ✗ %s/%d: %s", ticker, year, error)