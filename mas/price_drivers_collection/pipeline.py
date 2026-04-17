"""
Pipeline для обработки одного тикера за период.
Вызывает агента для каждого года, собирает результаты.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.core.base_agent import AgentContext, AgentResult
from agents.core.container import Container

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """
    Настройки pipeline обработки тикеров.

    Attributes:
        call_timeout_seconds: максимальное время ожидания одного вызова агента.
            По истечении вызов считается зависшим и возвращается ошибка.
            Не прерывает сам LLM-вызов (thread продолжает работу),
            но pipeline не блокируется.
        rate_limit_delay_seconds: задержка между вызовами агента.
            Используется для предотвращения 429 (rate limit) от LLM API.
            При ошибке предыдущего вызова задержка удваивается (backoff).
        rate_limit_backoff_on_error: множитель задержки при ошибке.
    """
    call_timeout_seconds: float = 30.0
    rate_limit_delay_seconds: float = 0.0
    rate_limit_backoff_on_error: float = 2.0


# Конфиг по умолчанию — без задержки (mock/тесты).
# Для реальных API передавай PipelineConfig(rate_limit_delay_seconds=1.0).
_DEFAULT_PIPELINE_CONFIG = PipelineConfig()


def _call_agent_with_timeout(
    agent,
    context: AgentContext,
    timeout_seconds: float,
) -> AgentResult:
    """
    Вызывает агента с ограничением по времени.

    Если агент не ответил за timeout_seconds — возвращает AgentResult с ошибкой.
    Сам поток продолжает выполняться (нельзя принудительно завершить thread в Python),
    но pipeline не блокируется.

    Args:
        agent: экземпляр агента
        context: контекст выполнения
        timeout_seconds: максимальное время ожидания

    Returns:
        AgentResult — успешный или с ошибкой таймаута
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
                    f"Проверьте доступность LLM API или увеличьте PipelineConfig.call_timeout_seconds."
                ),
            )


def process_ticker(
    container: Container,
    ticker: str,
    records: List[Dict[str, Any]],
    pipeline_config: Optional[PipelineConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Обрабатывает один тикер за период.

    Args:
        container: DI-контейнер с настроенным агентом
        ticker: символ тикера
        records: список записей [{year, price, dividend, yoy_change}, ...]
        pipeline_config: настройки rate limiting и timeout.
            None → используется _DEFAULT_PIPELINE_CONFIG (без задержки).
            Для реальных API: PipelineConfig(rate_limit_delay_seconds=1.0, call_timeout_seconds=30.0)

    Returns:
        Список результатов по каждому году
    """
    if not records:
        return []

    cfg = pipeline_config or _DEFAULT_PIPELINE_CONFIG

    # Агент создаётся один раз — он stateless.
    # Factory автоматически инжектит llm_adapter и prompt_manager.
    agent = container.factory.create_agent(
        agent_type="event_generation",
        config=container.config,
        skip_validation=True,
    )

    results = []
    current_delay = cfg.rate_limit_delay_seconds

    for i, record in enumerate(records):
        year = record["year"]
        logger.info("Processing %s / %d", ticker, year)

        # S4: rate limiting — задержка перед каждым вызовом (кроме первого)
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

        # M6: timeout на уровне pipeline
        result: AgentResult = _call_agent_with_timeout(
            agent=agent,
            context=context,
            timeout_seconds=cfg.call_timeout_seconds,
        )

        results.append({
            "ticker": ticker,
            "year": year,
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
            "prompt_version": result.prompt_version,
        })

        if result.success:
            # Сброс backoff при успехе
            current_delay = cfg.rate_limit_delay_seconds
            logger.info(
                "  ✓ %s/%d: %s (confidence=%.2f, %dms)",
                ticker, year,
                result.data.get("reason_short", "?"),
                result.data.get("confidence", 0),
                result.duration_ms or 0,
            )
        else:
            # S4: backoff при ошибке — увеличиваем задержку
            if cfg.rate_limit_delay_seconds > 0:
                current_delay = min(
                    current_delay * cfg.rate_limit_backoff_on_error,
                    60.0,  # максимум 60 секунд
                )
                logger.warning(
                    "  ✗ %s/%d: %s (следующая задержка: %.2fs)",
                    ticker, year, result.error, current_delay,
                )
            else:
                logger.warning("  ✗ %s/%d: %s", ticker, year, result.error)

    return results