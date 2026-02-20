#!/usr/bin/env python3
"""
Скрипт для запуска ETL процесса загрузки финансовых данных.
Загружает цены, дивиденды и сплиты для указанных тикеров.

Примеры использования:
    python scripts/run_etl.py                                     # все тикеры, все типы
    python scripts/run_etl.py --ticker JPM                        # только JPM
    python scripts/run_etl.py --ticker JPM,KO,MCD                 # несколько тикеров
    python scripts/run_etl.py --ticker "JPM KO MCD"               # тоже через пробел
    python scripts/run_etl.py --data-type prices                  # только цены
    python scripts/run_etl.py --ticker JPM --force               # перезаписать
    python scripts/run_etl.py --start 2000-01-01 --end 2025-12-31 # свои даты
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Type

# Добавляем путь к корню проекта для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import START_YEAR, END_YEAR, setup_project_dirs
from etl.fetch.companies import COMPANY_NAMES
from etl.fetch.price_fetcher import PriceFetcher
from etl.fetch.dividend_fetcher import DividendFetcher
from etl.fetch.split_fetcher import SplitFetcher
from etl.fetch.providers import DataSource

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent.parent / "etl_run.log")
    ]
)
logger = logging.getLogger("run_etl")

# Соответствие типов данных и классов фетчеров
FETCHER_CLASSES = {
    'prices': PriceFetcher,
    'dividends': DividendFetcher,
    'splits': SplitFetcher,
}


def parse_tickers(ticker_arg: Optional[str]) -> List[str]:
    """
    Преобразует аргумент командной строки в список тикеров.

    Поддерживает форматы:
    - "JPM"
    - "JPM,KO,MCD"
    - "JPM KO MCD"

    Parameters
    ----------
    ticker_arg : str, optional
        Строка с тикерами

    Returns
    -------
    List[str]
        Список тикеров в верхнем регистре
    """
    if not ticker_arg:
        return list(COMPANY_NAMES.keys())

    # Разделяем по запятой
    if ',' in ticker_arg:
        tickers = [t.strip().upper() for t in ticker_arg.split(',')]
    else:
        # Разделяем по пробелам
        tickers = [t.upper() for t in ticker_arg.split()]

    # Фильтруем пустые строки
    tickers = [t for t in tickers if t]

    return tickers


def validate_tickers(tickers: List[str]) -> List[str]:
    """
    Проверяет, что все тикеры есть в COMPANY_NAMES.

    Parameters
    ----------
    tickers : List[str]
        Список тикеров для проверки

    Returns
    -------
    List[str]
        Список некорректных тикеров
    """
    invalid = [t for t in tickers if t not in COMPANY_NAMES]
    if invalid:
        logger.warning(f"Обнаружены неизвестные тикеры: {invalid}")
        logger.info(f"Доступные тикеры: {sorted(COMPANY_NAMES.keys())}")
    return invalid


def get_fetcher_classes(data_type: Optional[str]) -> List[Type]:
    """
    Возвращает список классов фетчеров для обработки.

    Parameters
    ----------
    data_type : str, optional
        Тип данных ('prices', 'dividends', 'splits' или None для всех)

    Returns
    -------
    List[Type]
        Список классов фетчеров
    """
    if data_type:
        if data_type not in FETCHER_CLASSES:
            raise ValueError(
                f"Неизвестный тип данных: {data_type}. "
                f"Доступные: {list(FETCHER_CLASSES.keys())}"
            )
        return [FETCHER_CLASSES[data_type]]
    else:
        return list(FETCHER_CLASSES.values())


def should_skip_file(filepath: Path, force: bool) -> bool:
    """
    Проверяет, нужно ли пропустить файл.

    Parameters
    ----------
    filepath : Path
        Путь к файлу
    force : bool
        Флаг принудительной перезаписи

    Returns
    -------
    bool
        True если файл нужно пропустить
    """
    if force:
        return False
    return filepath.exists()


def run_fetcher(
        fetcher_class: Type,
        ticker: str,
        start_date: str,
        end_date: str,
        force: bool = False,
        **kwargs
) -> Dict[str, Any]:
    """
    Запускает конкретный фетчер для тикера.

    Parameters
    ----------
    fetcher_class : Type
        Класс фетчера
    ticker : str
        Тикер
    start_date : str
        Начальная дата
    end_date : str
        Конечная дата
    force : bool
        Перезаписывать существующие файлы
    **kwargs
        Дополнительные параметры для фетчера

    Returns
    -------
    Dict[str, Any]
        Результат выполнения
    """
    result = {
        'ticker': ticker,
        'data_type': fetcher_class.__name__.replace('Fetcher', '').lower(),
        'success': False,
        'filepath': None,
        'records': 0,
        'error': None,
        'skipped': False
    }

    try:
        # Создаем экземпляр фетчера
        fetcher = fetcher_class(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            **kwargs
        )

        # Проверяем, существует ли уже файл
        filename = fetcher._get_filename()
        filepath = fetcher.output_dir / filename

        if should_skip_file(filepath, force):
            logger.info(f"⏭️  {ticker} - {result['data_type']} уже существует, пропускаем")
            result['skipped'] = True
            result['filepath'] = filepath
            return result

        # Запускаем получение данных
        logger.info(f"🔄 {ticker} - загрузка {result['data_type']}...")
        data = fetcher.fetch()

        # Сохраняем
        saved_path = fetcher.run()

        result['success'] = True
        result['filepath'] = saved_path
        result['records'] = len(data)

        logger.info(f"✅ {ticker} - {result['data_type']}: {len(data)} записей")

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"❌ {ticker} - {result['data_type']}: {e}")

    return result


def print_summary(results: List[Dict[str, Any]], elapsed_time: float) -> None:
    """
    Выводит итоговую сводку выполнения.

    Parameters
    ----------
    results : List[Dict[str, Any]]
        Список результатов
    elapsed_time : float
        Время выполнения в секундах
    """
    logger.info("\n" + "=" * 60)
    logger.info("ИТОГОВАЯ СВОДКА ETL")
    logger.info("=" * 60)

    # Статистика
    total = len(results)
    successful = sum(1 for r in results if r['success'])
    skipped = sum(1 for r in results if r.get('skipped'))
    failed = sum(1 for r in results if not r['success'] and not r.get('skipped'))

    logger.info(f"Всего задач: {total}")
    logger.info(f"✅ Успешно: {successful}")
    logger.info(f"⏭️  Пропущено: {skipped}")
    logger.info(f"❌ Ошибок: {failed}")
    logger.info(f"⏱️  Время: {elapsed_time:.2f} сек")

    # Детали по ошибкам
    if failed:
        logger.info("\n" + "-" * 40)
        logger.info("ДЕТАЛИ ОШИБОК:")
        for r in results:
            if not r['success'] and not r.get('skipped') and r['error']:
                logger.error(f"  {r['ticker']} - {r['data_type']}: {r['error']}")

    # Информация по тикерам
    ticker_stats = {}
    for r in results:
        ticker = r['ticker']
        if ticker not in ticker_stats:
            ticker_stats[ticker] = {'total': 0, 'success': 0, 'failed': 0}

        ticker_stats[ticker]['total'] += 1
        if r['success']:
            ticker_stats[ticker]['success'] += 1
        elif not r.get('skipped'):
            ticker_stats[ticker]['failed'] += 1

    logger.info("\n" + "-" * 40)
    logger.info("СТАТИСТИКА ПО ТИКЕРАМ:")
    for ticker, stats in sorted(ticker_stats.items()):
        status = "✅" if stats['failed'] == 0 else "⚠️" if stats['failed'] < stats['total'] else "❌"
        logger.info(
            f"  {status} {ticker}: {stats['success']}/{stats['total']} "
            f"(ошибок: {stats['failed']})"
        )


def main():
    """Основная функция скрипта."""
    parser = argparse.ArgumentParser(
        description="ETL загрузка финансовых данных",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python scripts/run_etl.py
  python scripts/run_etl.py --ticker JPM
  python scripts/run_etl.py --ticker JPM,KO,MCD
  python scripts/run_etl.py --ticker "JPM KO MCD" --data-type prices
  python scripts/run_etl.py --start 2000-01-01 --end 2025-12-31 --force
        """
    )

    parser.add_argument(
        '--ticker',
        type=str,
        help='Тикер или список тикеров (через запятую или пробел). По умолчанию все'
    )

    parser.add_argument(
        '--data-type',
        type=str,
        choices=['prices', 'dividends', 'splits'],
        help='Тип данных для загрузки. По умолчанию все'
    )

    parser.add_argument(
        '--start',
        type=str,
        default=f"{START_YEAR}-01-01",
        help=f'Начальная дата (YYYY-MM-DD). По умолчанию {START_YEAR}-01-01'
    )

    parser.add_argument(
        '--end',
        type=str,
        default=f"{END_YEAR}-12-31",
        help=f'Конечная дата (YYYY-MM-DD). По умолчанию {END_YEAR}-12-31'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Перезаписывать существующие файлы'
    )

    parser.add_argument(
        '--frequency',
        type=str,
        default='YE',
        choices=['YE', 'QE', 'ME', 'DE'],
        help='Частота данных: YE(год), QE(квартал), ME(месяц), DE(день). По умолчанию YE'
    )

    parser.add_argument(
        '--source',
        type=str,
        default='yahoo',
        choices=['yahoo'],
        help='Источник данных. По умолчанию yahoo'
    )

    args = parser.parse_args()

    # Начало выполнения
    start_time = time.time()
    logger.info("🚀 ЗАПУСК ETL ПРОЦЕССА")
    logger.info("=" * 60)
    logger.info(f"Параметры: {args}")

    # Создаем директории
    setup_project_dirs()

    # Определяем список тикеров
    tickers = parse_tickers(args.ticker)
    invalid_tickers = validate_tickers(tickers)

    # Если есть неизвестные тикеры, спрашиваем продолжать ли
    if invalid_tickers and not args.ticker:
        # Если тикеры из аргумента неизвестны и это явно указанные тикеры
        logger.error(f"Обнаружены неизвестные тикеры: {invalid_tickers}")
        response = input("Продолжить с известными тикерами? (y/n): ")
        if response.lower() != 'y':
            logger.info("Выход по запросу пользователя")
            return

    # Фильтруем только известные тикеры
    valid_tickers = [t for t in tickers if t in COMPANY_NAMES]
    if not valid_tickers:
        logger.error("Нет валидных тикеров для обработки")
        return

    logger.info(f"Тикеры для обработки ({len(valid_tickers)}): {valid_tickers}")

    # Определяем классы фетчеров
    try:
        fetcher_classes = get_fetcher_classes(args.data_type)
    except ValueError as e:
        logger.error(e)
        return

    logger.info(f"Типы данных: {[cls.__name__ for cls in fetcher_classes]}")

    # Запускаем обработку
    results = []

    for fetcher_class in fetcher_classes:
        data_type_name = fetcher_class.__name__.replace('Fetcher', '')
        logger.info(f"\n--- ОБРАБОТКА ТИПА: {data_type_name} ---")

        for ticker in valid_tickers:
            company_name = COMPANY_NAMES.get(ticker, ticker)
            logger.info(f"\n📊 {ticker} - {company_name}")

            result = run_fetcher(
                fetcher_class=fetcher_class,
                ticker=ticker,
                start_date=args.start,
                end_date=args.end,
                force=args.force,
                frequency=args.frequency,
                data_source=DataSource(args.source)
            )
            results.append(result)

    # Итог
    elapsed_time = time.time() - start_time
    print_summary(results, elapsed_time)

    # Возвращаем код возврата
    if any(not r['success'] and not r.get('skipped') for r in results):
        sys.exit(1)