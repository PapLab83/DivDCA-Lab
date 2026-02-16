"""
Провайдеры данных для разных источников (Yahoo Finance, Alpha Vantage и т.д.)
Каждый провайдер реализует единый интерфейс DataProvider.
"""

from enum import Enum
from .base_provider import DataProvider
from .yahoo_provider import YahooProvider


class DataSource(Enum):
    """Поддерживаемые источники данных"""
    YAHOO = "yahoo"


def get_provider(source: DataSource = DataSource.YAHOO) -> DataProvider:
    """
    Фабрика провайдеров - создает провайдера для указанного источника.

    Args:
        source: источник данных (DataSource.YAHOO и т.д.)

    Returns:
        экземпляр провайдера, реализующего DataProvider

    Raises:
        ValueError: если источник не поддерживается
    """
    providers = {
        DataSource.YAHOO: YahooProvider,
    }

    provider_class = providers.get(source)
    if not provider_class:
        raise ValueError(f"Неподдерживаемый источник данных: {source}")

    return provider_class()


__all__ = [
    'DataProvider',
    'DataSource',
    'get_provider',
    'YahooProvider',
]