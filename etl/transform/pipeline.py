"""
Координатор трансформации для одного тикера.
Вызывает все шаги в правильном порядке.
"""
import logging
from typing import List

from . import readers
from .processors import dividend_aggregator
from . import annual_assembler
from .models import TransformedRecord

logger = logging.getLogger(__name__)


def run_for_ticker(ticker: str) -> List[TransformedRecord]:
    """
    Запускает полный цикл трансформации для одного тикера.

    Args:
        ticker: тикер (например, 'JPM')

    Returns:
        список TransformedRecord для сохранения

    Raises:
        FileNotFoundError: если нет файлов цен
        ValueError: при ошибках в данных
    """
    logger.info(f"Начало трансформации для {ticker}")

    # 1. Читаем все данные
    logger.debug(f"Чтение цен для {ticker}")
    prices = readers.read_prices(ticker)

    logger.debug(f"Чтение дивидендов для {ticker}")
    dividends = readers.read_dividends(ticker)

    logger.debug(f"Чтение сплитов для {ticker}")
    splits = readers.read_splits(ticker)

    logger.debug(f"Чтение reasons для {ticker}")
    reasons = readers.read_reasons(ticker)

    logger.info(f"Загружено: цен {len(prices)}, дивидендов {len(dividends)}, "
                f"сплитов {len(splits)}, причин {len(reasons)}")

    # 2. Агрегируем дивиденды по годам
    logger.debug("Агрегация дивидендов")

    # Определяем диапазон лет из цен для гарантии всех лет
    if prices:
        years = range(min(p.year for p in prices), max(p.year for p in prices) + 1)
        aggregated_dividends = dividend_aggregator.aggregate_with_gaps(dividends, years)
    else:
        logger.error(f"Нет данных о ценах для {ticker}")
        raise ValueError(f"Нет цен для {ticker}")

    logger.info(f"Дивиденды агрегированы: {len(aggregated_dividends)} лет")

    # 3. Собираем финальный датасет
    logger.debug("Сборка годового датасета")
    records = annual_assembler.assemble(
        prices=prices,
        dividends=aggregated_dividends,
        splits=splits,
        reasons=reasons
    )

    logger.info(f"Трансформация завершена: {len(records)} записей")

    return records


def validate_ticker_data(ticker: str) -> bool:
    """
    Быстрая проверка наличия всех необходимых файлов для тикера.

    Args:
        ticker: тикер

    Returns:
        True если минимальные данные есть, иначе False
    """
    try:
        prices = readers.read_prices(ticker)
        return len(prices) > 0
    except FileNotFoundError:
        return False