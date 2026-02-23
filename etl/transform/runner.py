"""
Batch-запуск трансформации для нескольких тикеров.
"""
import logging
import time
from pathlib import Path
from typing import List, Optional

from config.config import TRANSFORMED_DATA_DIR
from . import pipeline
from .writers import write_transformed_data  # создадим отдельно

logger = logging.getLogger(__name__)


def get_all_tickers_from_extracted() -> List[str]:
    """
    Получает список всех тикеров из файлов prices_*.jsonl в extracted/.

    Returns:
        список тикеров (уникальных)
    """
    from config.config import ETL_OUTPUT_DATA_DIR

    pattern = "prices_*.jsonl"
    files = list(ETL_OUTPUT_DATA_DIR.glob(pattern))

    tickers = []
    for f in files:
        # prices_JPM.jsonl -> JPM
        ticker = f.stem.replace("prices_", "")
        tickers.append(ticker)

    return sorted(tickers)


def run_for_ticker(ticker: str, force: bool = False) -> dict:
    """
    Запускает трансформацию для одного тикера.

    Args:
        ticker: тикер
        force: перезаписывать существующий файл

    Returns:
        dict с результатами: {
            'ticker': str,
            'success': bool,
            'records': int,
            'error': Optional[str],
            'skipped': bool,
            'duration': float
        }
    """
    start_time = time.time()
    result = {
        'ticker': ticker,
        'success': False,
        'records': 0,
        'error': None,
        'skipped': False,
        'duration': 0.0
    }

    try:
        # Проверяем, существует ли уже выходной файл
        output_file = TRANSFORMED_DATA_DIR / f"{ticker}.jsonl"
        if output_file.exists() and not force:
            logger.info(f"⏭️  {ticker}: файл уже существует, пропускаем")
            result['skipped'] = True
            result['success'] = True
            return result

        # Запускаем pipeline
        logger.info(f"🔄 {ticker}: запуск трансформации")
        records = pipeline.run_for_ticker(ticker)

        # Сохраняем результат
        write_transformed_data(ticker, records)

        result['success'] = True
        result['records'] = len(records)
        logger.info(f"✅ {ticker}: сохранено {len(records)} записей")

    except FileNotFoundError as e:
        result['error'] = f"Файл не найден: {e}"
        logger.error(f"❌ {ticker}: {result['error']}")
    except ValueError as e:
        result['error'] = f"Ошибка данных: {e}"
        logger.error(f"❌ {ticker}: {result['error']}")
    except Exception as e:
        result['error'] = f"Неизвестная ошибка: {e}"
        logger.error(f"❌ {ticker}: {result['error']}")

    result['duration'] = time.time() - start_time
    return result


def run_for_tickers(tickers: List[str], force: bool = False) -> List[dict]:
    """
    Запускает трансформацию для списка тикеров.

    Args:
        tickers: список тикеров
        force: перезаписывать существующие файлы

    Returns:
        список результатов для каждого тикера
    """
    results = []

    for ticker in tickers:
        result = run_for_ticker(ticker, force)
        results.append(result)

    return results


def run_all(force: bool = False, tickers: Optional[List[str]] = None) -> List[dict]:
    """
    Запускает трансформацию для всех или указанных тикеров.

    Args:
        force: перезаписывать существующие файлы
        tickers: если указаны, запускает только их

    Returns:
        список результатов
    """
    if tickers is None:
        tickers = get_all_tickers_from_extracted()

    if not tickers:
        logger.warning("Нет тикеров для обработки")
        return []

    logger.info(f"Запуск трансформации для {len(tickers)} тикеров: {', '.join(tickers[:5])}...")

    start_time = time.time()
    results = run_for_tickers(tickers, force)
    total_time = time.time() - start_time

    # Статистика
    successful = sum(1 for r in results if r['success'] and not r.get('skipped'))
    skipped = sum(1 for r in results if r.get('skipped'))
    failed = sum(1 for r in results if not r['success'])

    logger.info(f"Завершено за {total_time:.2f} сек: ✅ {successful} обработано, "
                f"⏭️ {skipped} пропущено, ❌ {failed} ошибок")

    return results