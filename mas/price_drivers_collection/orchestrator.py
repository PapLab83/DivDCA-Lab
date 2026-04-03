"""
Оркестратор: координация обработки всех тикеров.
"""
import logging
from typing import Any, Dict, List

from agents.core.container import Container
from mas.price_drivers_collection.pipeline import process_ticker

logger = logging.getLogger(__name__)


def run_collection(
    container: Container,
    tickers_data: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Запускает pipeline для каждого тикера.

    Args:
        container: DI-контейнер
        tickers_data: список [{ticker, records: [...]}, ...]

    Returns:
        {ticker: [результаты по годам]}
    """
    all_results: Dict[str, List[Dict[str, Any]]] = {}
    total_success = 0
    total_fail = 0

    for ticker_data in tickers_data:
        ticker = ticker_data["ticker"]
        records = ticker_data["records"]

        logger.info("=" * 50)
        logger.info("Тикер: %s (%d записей)", ticker, len(records))
        logger.info("=" * 50)

        results = process_ticker(container, ticker, records)
        all_results[ticker] = results

        for r in results:
            if r["success"]:
                total_success += 1
            else:
                total_fail += 1

    logger.info("=" * 50)
    logger.info(
        "Итого: %d успешно, %d ошибок из %d",
        total_success, total_fail, total_success + total_fail,
    )
    logger.info("=" * 50)

    return all_results