"""
Pipeline для обработки одного тикера за период.
Вызывает агента для каждого года, собирает результаты.
"""
import logging
from typing import Any, Dict, List

from agents.core.base_agent import AgentContext, AgentResult
from agents.core.container import Container

logger = logging.getLogger(__name__)


def process_ticker(
    container: Container,
    ticker: str,
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Обрабатывает один тикер за период.

    Args:
        container: DI-контейнер с настроенным агентом
        ticker: символ тикера
        records: список записей [{year, price, dividend, yoy_change}, ...]

    Returns:
        Список результатов по каждому году
    """
    if not records:
        return []

    # Агент создаётся один раз — он stateless.
    # Factory автоматически инжектит llm_adapter и prompt_manager.
    agent = container.factory.create_agent(
        agent_type="event_generation",
        config=container.config,
        skip_validation=True,
    )

    results = []

    for record in records:
        year = record["year"]
        logger.info("Processing %s / %d", ticker, year)

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

        result: AgentResult = agent.execute(context)

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
            logger.info(
                "  ✓ %s/%d: %s (confidence=%.2f, %dms)",
                ticker, year,
                result.data.get("reason_short", "?"),
                result.data.get("confidence", 0),
                result.duration_ms or 0,
            )
        else:
            logger.warning("  ✗ %s/%d: %s", ticker, year, result.error)

    return results