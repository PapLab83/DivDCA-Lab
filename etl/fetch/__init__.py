"""
Модуль для получения данных из внешних источников.
Содержит фетчеры для разных типов данных и провайдеры для разных API.
"""

from .price_fetcher import PriceFetcher
from .dividend_fetcher import DividendFetcher
from .split_fetcher import SplitFetcher
from .companies import COMPANY_NAMES

__all__ = [
    'PriceFetcher',
    'DividendFetcher',
    'SplitFetcher',
    'COMPANY_NAMES'
]