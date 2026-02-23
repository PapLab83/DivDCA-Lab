#!/usr/bin/env python3
"""
Скрипт для запуска трансформации данных.
Примеры:
    python scripts/transform.py                    # все тикеры
    python scripts/transform.py --ticker JPM       # один тикер
    python scripts/transform.py --ticker JPM,KO    # несколько через запятую
    python scripts/transform.py --ticker "JPM KO"  # несколько через пробел
    python scripts/transform.py --force             # перезаписать существующие
"""
import argparse
import logging
import sys
import traceback
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

# Настройка логирования
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
    parser.add_argument('--ticker', type=str, help='Тикер или список')
    parser.add_argument('--force', action='store_true', help='Перезаписать существующие')
    parser.add_argument('--debug', action='store_true', help='Режим отладки')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Режим отладки включен")

    logger.info("🚀 ЗАПУСК ТРАНСФОРМАЦИИ")
    logger.info(f"Параметры: force={args.force}, ticker={args.ticker}, debug={args.debug}")

    # Отладочная информация
    logger.debug(f"sys.path: {sys.path}")
    logger.debug(f"Текущая директория: {Path.cwd()}")
    logger.debug(f"__file__: {__file__}")

    try:
        # Пробуем импортировать с отловом ошибок
        try:
            from etl.transform.runner import run_all, run_for_tickers
            logger.debug("Импорт runner успешен")
        except ImportError as e:
            logger.error(f"Ошибка импорта runner: {e}")
            logger.error(traceback.format_exc())

            # Проверяем доступность config
            try:
                import config
                logger.error(f"config найден в: {config.__file__}")
                from config import config as config_module
                logger.error(f"Доступные атрибуты config: {[a for a in dir(config_module) if a.isupper()]}")
            except ImportError as e2:
                logger.error(f"config не найден: {e2}")

            sys.exit(1)

        if args.ticker:
            tickers = parse_tickers(args.ticker)
            logger.info(f"Обработка тикеров: {tickers}")
            results = run_for_tickers(tickers, force=args.force)
        else:
            logger.info("Обработка всех доступных тикеров")
            results = run_all(force=args.force)

        # Проверяем ошибки
        failed = [r for r in results if not r['success']]
        if failed:
            logger.error(f"❌ Ошибок: {len(failed)}")
            for f in failed:
                logger.error(f"  {f['ticker']}: {f['error']}")
            sys.exit(1)
        else:
            logger.info("✅ Все тикеры обработаны успешно")

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()