"""
Оркестратор: координация обработки всех тикеров.
"""
import logging
from typing import Any, Dict, List, Optional

from agents.core.container import Container
from mas.price_drivers_collection.pipeline import process_ticker

logger = logging.getLogger(__name__)


def run_collection(
    container: Container,
    tickers_data: List[Dict[str, Any]],
    profile=None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Запускает pipeline для каждого тикера.

    Args:
        container: DI-контейнер с настроенным агентом
        tickers_data: список [{ticker, records: [...]}, ...]
        profile: UserProfile (опционально).
            Если передан — результаты каждого тикера фильтруются
            по порогам confidence и dividend_yield из профиля.

    Returns:
        {ticker: [результаты по годам]}
        Ключи словаря — реальные тикеры (не анонимные).
    """
    all_results: Dict[str, List[Dict[str, Any]]] = {}
    total_success = 0
    total_fail = 0
    total_filtered = 0

    if profile is not None:
        logger.info("UserProfile активен: %s", profile)

    for ticker_data in tickers_data:
        ticker = ticker_data["ticker"]
        records = ticker_data["records"]

        logger.info("=" * 50)
        logger.info("Тикер: %s (%d записей)", ticker, len(records))
        logger.info("=" * 50)

        results = process_ticker(
            container,
            ticker,
            records,
            profile=profile,
        )
        all_results[ticker] = results

        # Подсчёт статистики
        # Если profile активен — results уже отфильтрованы,
        # поэтому считаем отдельно сырые записи для статистики filtered.
        raw_count = len(ticker_data["records"])
        returned_count = len(results)

        for r in results:
            if r["success"]:
                total_success += 1
            else:
                total_fail += 1

        if profile is not None:
            filtered_count = raw_count - returned_count
            total_filtered += filtered_count
            if filtered_count > 0:
                logger.info(
                    "Тикер %s: %d записей отфильтровано профилем [%s]",
                    ticker, filtered_count, profile.level.value,
                )

    logger.info("=" * 50)
    logger.info(
        "Итого: %d успешно, %d ошибок из %d",
        total_success,
        total_fail,
        total_success + total_fail,
    )
    if profile is not None and total_filtered > 0:
        logger.info(
            "Отфильтровано профилем [%s]: %d записей",
            profile.level.value,
            total_filtered,
        )
    logger.info("=" * 50)

    return all_results