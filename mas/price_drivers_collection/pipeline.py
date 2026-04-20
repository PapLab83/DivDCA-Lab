"""
Pipeline для обработки одного тикера за период.
Вызывает агента для каждого года, собирает результаты.
ThreadPoolExecutor зафиксирован как tech debt (TD-001):
    Текущая реализация создаёт executor на каждый вызов агента.
    При масштабировании (>100 тикеров) заменить на shared executor
    с timeout через concurrent.futures.wait на уровне оркестратора.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agents.core.base_agent import AgentContext, AgentResult
from agents.core.container import Container
from agents.core.profiles import UserProfile
from agents.core.profiles.profile_validator import ProfileValidator

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """
    Настройки pipeline обработки тикеров.

    Attributes:
        call_timeout_seconds: максимальное время ожидания одного вызова агента.
        rate_limit_delay_seconds: задержка между вызовами агента.
        rate_limit_backoff_on_error: множитель задержки при ошибке.
    """
    call_timeout_seconds: float = 30.0
    rate_limit_delay_seconds: float = 0.0
    rate_limit_backoff_on_error: float = 2.0


_DEFAULT_PIPELINE_CONFIG = PipelineConfig()


def _call_agent_with_timeout(
    agent,
    context: AgentContext,
    timeout_seconds: float,
) -> AgentResult:
    """
    Вызывает агента с ограничением по времени.

    Если агент не ответил за timeout_seconds — возвращает AgentResult с ошибкой.

    TD-001: ThreadPoolExecutor создаётся на каждый вызов.
    При масштабировании заменить на shared executor в process_ticker.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(agent.execute, context)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
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
                    f"Проверьте доступность LLM API или увеличьте "
                    f"PipelineConfig.call_timeout_seconds."
                ),
            )


def process_ticker(
    container: Container,
    ticker: str,
    records: List[Dict[str, Any]],
    pipeline_config: Optional[PipelineConfig] = None,
    profile: Optional[UserProfile] = None,
) -> List[Dict[str, Any]]:
    """
    Обрабатывает один тикер за период.

    Args:
        container: DI-контейнер с настроенным агентом
        ticker: символ тикера. Ожидается что данные уже анонимизированы
                на уровне БД — pipeline не выполняет анонимизацию.
        records: список записей [{year, price, dividend, yoy_change}, ...]
        pipeline_config: настройки rate limiting и timeout
        profile: UserProfile (опционально).
            Если передан — результаты фильтруются по профилю.

    Returns:
        Список результатов по каждому году.
    """
    if not records:
        return []

    cfg = pipeline_config or _DEFAULT_PIPELINE_CONFIG
    agent = container.factory.create_agent(
        agent_type="event_generation",
        config=container.config,
    )

    results = []
    current_delay = cfg.rate_limit_delay_seconds

    for i, record in enumerate(records):
        year = record["year"]
        logger.info("Processing %s / %d", ticker, year)

        if i > 0 and current_delay > 0:
            logger.debug(
                "Rate limit delay: %.2fs перед %s/%d",
                current_delay, ticker, year,
            )
            time.sleep(current_delay)

        context = AgentContext(
            agent_id=f"{ticker}-{year}",
            task="event_generation",
            metadata={
                "ticker": ticker,
                "year": year,
                "price": record["price"],
                "dividend": record["dividend"],
                "yoy_change": record["yoy_change"],
            },
        )

        result: AgentResult = _call_agent_with_timeout(
            agent=agent,
            context=context,
            timeout_seconds=cfg.call_timeout_seconds,
        )

        results.append({
            "ticker": ticker,
            "year": year,
            "price": record["price"],
            "dividend": record["dividend"],
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
            "prompt_version": result.prompt_version,
        })

        if result.success:
            current_delay = cfg.rate_limit_delay_seconds
            logger.info(
                "  ✓ %s/%d: %s (confidence=%.2f, %dms)",
                ticker, year,
                result.data.get("reason_short", "?"),
                result.data.get("confidence", 0),
                result.duration_ms or 0,
            )
        else:
            if cfg.rate_limit_delay_seconds > 0:
                current_delay = min(
                    current_delay * cfg.rate_limit_backoff_on_error,
                    60.0,
                )
                logger.warning(
                    "  ✗ %s/%d: %s (следующая задержка: %.2fs)",
                    ticker, year, result.error, current_delay,
                )
            else:
                logger.warning("  ✗ %s/%d: %s", ticker, year, result.error)

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