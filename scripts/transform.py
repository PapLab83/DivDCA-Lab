#!/usr/bin/env python3
"""
Скрипт для запуска трансформации данных.
Примеры:
    python scripts/transform.py --all                    # все тикеры
    python scripts/transform.py --ticker JPM             # один тикер
    python scripts/transform.py --ticker JPM,KO          # несколько
    python scripts/transform.py --all --force            # все с перезаписью
"""
import argparse
import logging
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("transform")


def parse_tickers(ticker_arg: str) -> list[str]:
    """Парсит строку с тикерами."""
    if not ticker_arg:
        return []
    tickers = ticker_arg.replace(',', ' ').split()
    return [t.strip().upper() for t in tickers if t.strip()]


def main():
    parser = argparse.ArgumentParser(description="Трансформация данных")

    # Группа взаимоисключающих аргументов
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--ticker', type=str, help='Тикер или список (через запятую или пробел)')
    group.add_argument('--all', action='store_true', help='Обработать все доступные тикеры')

    parser.add_argument('--force', action='store_true', help='Перезаписать существующие файлы')
    parser.add_argument('--debug', action='store_true', help='Режим отладки')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Режим отладки включен")

    logger.info("🚀 ЗАПУСК ТРАНСФОРМАЦИИ")
    logger.info(f"Параметры: force={args.force}, debug={args.debug}")

    try:
        from etl.transform.runner import run_all, run_for_tickers

        if args.all:
            logger.info("Обработка всех доступных тикеров")
            results = run_all(force=args.force)
        else:
            tickers = parse_tickers(args.ticker)
            logger.info(f"Обработка тикеров: {tickers}")
            results = run_for_tickers(tickers, force=args.force)

        # Проверяем ошибки
        failed = [r for r in results if not r['success']]
        if failed:
            logger.error(f"❌ Ошибок: {len(failed)}")
            for f in failed:
                logger.error(f"  {f['ticker']}: {f['error']}")
            sys.exit(1)
        else:
            logger.info("✅ Все тикеры обработаны успешно")

    except ImportError as e:
        logger.error(f"Ошибка импорта: {e}")
        if args.debug:
            logger.error(traceback.format_exc())
        sys.exit(1)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        if args.debug:
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()