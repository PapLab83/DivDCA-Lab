"""
Конфигурационный файл для DivDCA Lab (прототип).
Все изменяемые параметры стратегии и пути здесь.
"""

import os
from pathlib import Path

# ==================== ПАРАМЕТРЫ СТРАТЕГИИ ====================
ANNUAL_INVESTMENT = 12000.0  # Фиксированная сумма ежегодных инвестиций (USD)
START_YEAR = 2010  # Год начала инвестирования (анализа)
END_YEAR = 2023  # Год окончания инвестирования (анализа)
TICKER = "JNJ"  # Тикер анализируемой бумаги
COMPANY_NAMES = {
    'JNJ': 'Johnson & Johnson',
    'PG': 'Procter & Gamble',
    'KO': 'Coca-Cola',
    'MCD': 'McDonald\'s',
    'O': 'Realty Income',
    'JPM': 'JPMorgan Chase',
    'BAC': 'Bank of America',
    'BLK': 'BlackRock',
    'AVGO': 'Broadcom Inc.',
    'TXN': 'Texas Instruments',
    'XOM': 'Exxon Mobil',
    'CVX': 'Chevron',
    'MMM': '3M Company',
    'ABBV': 'AbbVie',
    'AMT': 'American Tower',
    'CCI': 'Crown Castle',
    'MSFT': 'Microsoft',
    'AAPL': 'Apple',
    'LOW': 'Lowe\'s',
    'HD': 'Home Depot',
    'PM': 'Philip Morris',
    'MO': 'Altria Group',
    'KHC': 'Kraft Heinz',
    'PEP': 'PepsiCo',
    'WMT': 'Walmart',
    'TGT': 'Target',
    'NEE': 'NextEra Energy',
    'SO': 'Southern Company',
    'DUK': 'Duke Energy',
    'IBM': 'International Business Machines',
    'VZ': 'Verizon'
}

# Обработка дивидендов. True - реинвестировать, False - копить как кэш.
# ВНИМАНИЕ: На текущий момент реализована ТОЛЬКО стратегия с реинвестированием (True).
REINVEST_DIVIDENDS = True

# ==================== ПУТИ И ДИРЕКТОРИИ ====================
# Базовые директории (относительно корня проекта)
BASE_DIR = Path(__file__).parent.parent  # Корень проекта (уровень выше src/)
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"  # Исходные JSONL-файлы (TICKER.jsonl)
PROCESSED_DATA_DIR = DATA_DIR / "processed"  # Кэш обработанных данных (опционально)
REPORTS_DIR = DATA_DIR / "reports"
TABLES_DIR = REPORTS_DIR / "tables"  # Таблицы (CSV, Excel, JSON)
GRAPHS_DIR = REPORTS_DIR / "graphs"  # HTML-отчёты с графиками

# Форматы вывода табличных данных
OUTPUT_TABLE_FORMATS = ["xlsx", "json"]  # Доступные форматы

# ==================== НАСТРОЙКИ ЛОГИРОВАНИЯ ====================
LOG_LEVEL = "INFO"  # Уровень логирования: DEBUG, INFO, WARNING, ERROR
LOG_FILE = BASE_DIR / "divdca_lab.log"  # Файл для логов (опционально)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def setup_project_dirs() -> None:
    """Создаёт все необходимые директории проекта, если они не существуют."""
    dirs_to_create = [
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        TABLES_DIR,
        GRAPHS_DIR,
    ]
    for directory in dirs_to_create:
        directory.mkdir(parents=True, exist_ok=True)
        # Создаем пустой .gitkeep файл, чтобы пустые директории коммитились в Git
        (directory / ".gitkeep").touch(exist_ok=True)


def generate_report_filename(
    prefix: str,
    ticker: str = TICKER,
    start_year: int = START_YEAR,
    end_year: int = END_YEAR,
    annual_investment: float = ANNUAL_INVESTMENT,
    reinvest_div: bool = REINVEST_DIVIDENDS,
) -> str:
    """
    Генерирует базовое имя файла для отчётов по шаблону:
    {prefix}_{TICKER}_{START_YEAR}_{END_YEAR}_{INVESTMENT}_{REINVEST}.{ext}

    Параметры:
        prefix: Префикс, обозначающий тип отчёта ('table', 'report' и т.д.)
    """
    reinvest_suffix = "rein" if reinvest_div else "cash"
    investment_int = int(annual_investment)
    return f"{prefix}_{ticker}_{start_year}_{end_year}_{investment_int}_{reinvest_suffix}"


def get_data_path(ticker: str = TICKER) -> Path:
    """
    Возвращает полный путь к файлу с исходными данными для указанного тикера.
    Ожидаемое имя файла: {TICKER}.jsonl
    """
    return RAW_DATA_DIR / f"{ticker.upper()}.jsonl"


# ==================== ВАЛИДАЦИЯ КОНФИГУРАЦИИ ====================
def validate_config() -> None:
    """Проверяет корректность заданных параметров конфигурации."""
    if not REINVEST_DIVIDENDS:
        raise NotImplementedError(
            "Реинвестирование дивидендов отключено (REINVEST_DIVIDENDS=False). "
            "На текущий момент реализована ТОЛЬКО стратегия с реинвестированием."
        )

    if START_YEAR > END_YEAR:
        raise ValueError(f"START_YEAR ({START_YEAR}) должен быть меньше END_YEAR ({END_YEAR})")

    if ANNUAL_INVESTMENT <= 0:
        raise ValueError(f"ANNUAL_INVESTMENT ({ANNUAL_INVESTMENT}) должен быть положительным числом.")

    if not TICKER or not isinstance(TICKER, str):
        raise ValueError(f"TICKER должен быть непустой строкой. Получено: {TICKER}")

    # Проверяем существование файла с данными (предупреждение)
    data_file = get_data_path()
    if not data_file.exists():
        print(f"Предупреждение: Файл с данными не найден: {data_file}")


# ==================== ИНИЦИАЛИЗАЦИЯ ====================
# Автоматически создаём директории и валидируем конфиг
try:
    setup_project_dirs()
    validate_config()
except (NotImplementedError, ValueError) as e:
    print(f"ОШИБКА КОНФИГУРАЦИИ: {e}")
    print("Исправьте параметры в config.py перед запуском.")
    raise