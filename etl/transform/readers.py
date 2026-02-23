"""
Модуль для чтения данных из extracted/.
Все функции возвращают списки Pydantic моделей.
"""
import json
from pathlib import Path
from typing import Type, TypeVar, List
from pydantic import BaseModel

from config.config import ETL_OUTPUT_DATA_DIR
from .models import RawPrice, RawDividend, RawSplit, RawReason

T = TypeVar('T', bound=BaseModel)


def _read_jsonl(filepath: Path, model: Type[T]) -> List[T]:
    """
    Универсальная функция для чтения JSONL файлов.

    Args:
        filepath: путь к файлу
        model: Pydantic модель для парсинга

    Returns:
        список объектов модели

    Raises:
        FileNotFoundError: если файл не существует
        ValueError: если файл пустой или невалидный JSON
    """
    if not filepath.exists():
        raise FileNotFoundError(f"Файл не найден: {filepath}")

    records = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(model.model_validate(data))
            except json.JSONDecodeError as e:
                raise ValueError(f"Ошибка JSON в строке {line_num}: {e}")
            except Exception as e:
                raise ValueError(f"Ошибка валидации в строке {line_num}: {e}")

    if not records:
        raise ValueError(f"Файл {filepath} пустой или не содержит валидных данных")

    return records


def read_prices(ticker: str) -> List[RawPrice]:
    """
    Читает цены для тикера из extracted/prices_{ticker}.jsonl

    Args:
        ticker: тикер (например, 'JPM')

    Returns:
        список RawPrice, отсортированный по дате
    """
    filepath = ETL_OUTPUT_DATA_DIR / f"prices_{ticker.upper()}.jsonl"
    records = _read_jsonl(filepath, RawPrice)
    return sorted(records, key=lambda x: x.date)


def read_dividends(ticker: str) -> List[RawDividend]:
    """
    Читает дивиденды для тикера из extracted/dividends_{ticker}.jsonl

    Args:
        ticker: тикер (например, 'JPM')

    Returns:
        список RawDividend, отсортированный по дате
    """
    filepath = ETL_OUTPUT_DATA_DIR / f"dividends_{ticker.upper()}.jsonl"
    records = _read_jsonl(filepath, RawDividend)
    return sorted(records, key=lambda x: x.date)


def read_splits(ticker: str) -> List[RawSplit]:
    """
    Читает сплиты для тикера из extracted/splits_{ticker}.jsonl

    Args:
        ticker: тикер (например, 'JPM')

    Returns:
        список RawSplit, отсортированный по дате
    """
    filepath = ETL_OUTPUT_DATA_DIR / f"splits_{ticker.upper()}.jsonl"

    # Сплитов может не быть — возвращаем пустой список
    if not filepath.exists():
        return []

    records = _read_jsonl(filepath, RawSplit)
    return sorted(records, key=lambda x: x.date)


def read_reasons(ticker: str) -> List[RawReason]:
    """Читает reasons для тикера из extracted/reasons_{ticker}.jsonl"""
    filepath = ETL_OUTPUT_DATA_DIR / f"reasons_{ticker.upper()}.jsonl"

    if not filepath.exists():
        return []

    return _read_jsonl(filepath, RawReason)  # 👏 переиспользуем