# etl/transform/writers.py
import json
from pathlib import Path
from typing import List

from config.config import TRANSFORMED_DATA_DIR
from .models import TransformedRecord


def write_transformed_data(ticker: str, records: List[TransformedRecord]) -> Path:
    """
    Сохраняет трансформированные данные в JSONL.

    Args:
        ticker: тикер
        records: список записей

    Returns:
        путь к сохраненному файлу
    """
    filepath = TRANSFORMED_DATA_DIR / f"{ticker}.jsonl"

    with open(filepath, 'w', encoding='utf-8') as f:
        for record in records:
            # Конвертируем дату в строку
            data = record.model_dump()
            data['date'] = data['date'].isoformat()
            f.write(json.dumps(data, ensure_ascii=False) + '\n')

    return filepath