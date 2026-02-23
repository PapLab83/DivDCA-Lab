"""
Pydantic модели для данных в этапе TRANSFORM.
Yahoo Finance уже дает скорректированные на сплиты цены и дивиденды.
"""
from datetime import date
from typing import Optional, List
from pydantic import BaseModel, Field


# ===== ВХОДНЫЕ ДАННЫЕ (из extracted/) =====

class RawPrice(BaseModel):
    """Цена из extracted/prices_*.jsonl (уже скорректирована на сплиты)"""
    date: date
    year: int
    price: float = Field(ge=0)


class RawDividend(BaseModel):
    """Дивиденд из extracted/dividends_*.jsonl (уже скорректирован на сплиты)"""
    date: date
    year: int
    dividend: float = Field(ge=0)


class RawSplit(BaseModel):
    """Сплит из extracted/splits_*.jsonl (только для информации в reason_long)"""
    date: date
    year: int
    split_ratio: float = Field(gt=0)
    split_type: Optional[str] = None


class RawReason(BaseModel):
    """Причина из extracted/reasons_*.json (от GPT или вручную)"""
    ticker: str
    year: int
    reason_short: Optional[str] = None
    reason_long: Optional[str] = None
    generated_at: Optional[date] = None


# ===== ДАННЫЕ ПОСЛЕ PROCESSORS =====

class AggregatedDividend(BaseModel):
    """
    Дивиденды, агрегированные по году (processor: dividend_aggregator)
    """
    year: int
    total_dividend: float = Field(ge=0)  # сумма за год
    payment_count: int = Field(ge=0)      # количество выплат


# ===== ПРОМЕЖУТОЧНЫЙ ДАТАФРЕЙМ ПЕРЕД ASSEMBLER =====

class YearlyData(BaseModel):
    """
    Все данные по одному году перед финальной сборкой.
    """
    year: int
    price_date: Optional[date] = None
    price: Optional[float] = None          # цена на 31 декабря
    total_dividend: float = 0.0             # сумма дивидендов за год
    dividend_count: int = 0
    splits: List[RawSplit] = Field(default_factory=list)  # для обогащения reason
    reason: Optional[RawReason] = None


# ===== ВЫХОДНЫЕ ДАННЫЕ (в transformed/) =====

class TransformedRecord(BaseModel):
    """
    Финальная запись для transformed/{TICKER}.jsonl.
    """
    date: date  # всегда 31 декабря
    year: int
    price: float = Field(ge=0)
    div_annual: float = Field(ge=0)
    reason_short: Optional[str] = None
    reason_long: Optional[str] = None


class TransformedData(BaseModel):
    """Коллекция записей для одного тикера"""
    ticker: str
    records: List[TransformedRecord]
    generated_at: date = Field(default_factory=date.today)