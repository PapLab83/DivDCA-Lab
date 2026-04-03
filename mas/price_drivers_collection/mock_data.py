"""
Мок-данные для тестирования pipeline.
Структура: список тикеров, каждый с записями за период.
"""
from typing import Any, Dict, List, TypedDict


class TickerYearRecord(TypedDict):
    year: int
    price: float
    dividend: float
    yoy_change: float


class TickerData(TypedDict):
    ticker: str
    records: List[TickerYearRecord]


MOCK_TICKERS: List[TickerData] = [
    {
        "ticker": "AAPL",
        "records": [
            {"year": 2019, "price": 73.41, "dividend": 0.75, "yoy_change": 5.5},
            {"year": 2020, "price": 131.96, "dividend": 0.80, "yoy_change": 6.7},
            {"year": 2021, "price": 177.57, "dividend": 0.85, "yoy_change": 6.3},
            {"year": 2022, "price": 129.93, "dividend": 0.91, "yoy_change": 7.1},
        ],
    },
    {
        "ticker": "JNJ",
        "records": [
            {"year": 2019, "price": 145.87, "dividend": 3.75, "yoy_change": 5.6},
            {"year": 2020, "price": 157.38, "dividend": 3.98, "yoy_change": 6.1},
            {"year": 2021, "price": 168.85, "dividend": 4.19, "yoy_change": 5.3},
        ],
    },
    {
        "ticker": "T",
        "records": [
            {"year": 2019, "price": 39.08, "dividend": 2.04, "yoy_change": 2.0},
            {"year": 2020, "price": 28.76, "dividend": 2.08, "yoy_change": 2.0},
            {"year": 2021, "price": 24.51, "dividend": 2.08, "yoy_change": 0.0},
            {"year": 2022, "price": 18.56, "dividend": 1.11, "yoy_change": -46.6},
        ],
    },
]