"""
Реализация провайдера данных для Yahoo Finance.
Использует библиотеку yfinance для получения данных и приводит их к единому формату.
"""

import pandas as pd
import yfinance as yf
import logging

from .base_provider import DataProvider

# Настройка логгера
logger = logging.getLogger(__name__)


class YahooProvider(DataProvider):
    """
    Провайдер данных из Yahoo Finance.

    Адаптирует специфичный для Yahoo формат данных к единому контракту DataProvider.
    Использует библиотеку yfinance под капотом.
    """

    def __init__(self):
        """Инициализация провайдера Yahoo Finance."""
        self._ticker_cache = {}  # Простой кеш для объектов тикеров

    def _get_ticker(self, ticker: str) -> yf.Ticker:
        """
        Получает или создает объект тикера (с кешированием).

        Parameters
        ----------
        ticker : str
            Тикер инструмента

        Returns
        -------
        yf.Ticker
            Объект тикера Yahoo Finance
        """
        if ticker not in self._ticker_cache:
            self._ticker_cache[ticker] = yf.Ticker(ticker)
        return self._ticker_cache[ticker]

    def get_prices(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """
        Получение исторических цен из Yahoo Finance.

        Parameters
        ----------
        ticker : str
            Тикер инструмента (например, 'JPM', 'AAPL')
        start : str
            Начальная дата в формате 'YYYY-MM-DD'
        end : str
            Конечная дата в формате 'YYYY-MM-DD'

        Returns
        -------
        pd.DataFrame
            DataFrame с индексом DatetimeIndex и колонками Open, High, Low, Close, Volume
        """
        logger.info(f"Загрузка цен для {ticker} за период {start} - {end}")

        try:
            # Получаем сырые данные от Yahoo
            ticker_obj = self._get_ticker(ticker)
            raw_data = ticker_obj.history(start=start, end=end)

            if raw_data.empty:
                logger.warning(f"Нет данных о ценах для {ticker} за указанный период")
                # Возвращаем пустой DataFrame с правильными колонками
                return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

            # Приводим к единому формату
            result = pd.DataFrame(index=raw_data.index)
            result['Open'] = raw_data['Open'].astype(float)
            result['High'] = raw_data['High'].astype(float)
            result['Low'] = raw_data['Low'].astype(float)
            result['Close'] = raw_data['Close'].astype(float)
            result['Volume'] = raw_data['Volume'].astype(float)

            # Гарантируем DatetimeIndex
            result = self._ensure_datetime_index(result)

            # Заполняем пропуски (выходные и праздники)
            result = self._fill_missing_dates(result, freq='D')

            logger.info(f"Загружено {len(result)} записей о ценах для {ticker}")
            return result

        except Exception as e:
            logger.error(f"Ошибка загрузки цен для {ticker}: {e}")
            raise

    def get_dividends(self, ticker: str, start: str, end: str) -> pd.Series:
        """
        Получение истории дивидендов из Yahoo Finance.

        Parameters
        ----------
        ticker : str
            Тикер инструмента
        start : str
            Начальная дата в формате 'YYYY-MM-DD'
        end : str
            Конечная дата в формате 'YYYY-MM-DD'

        Returns
        -------
        pd.Series
            Series с индексом DatetimeIndex (даты выплат) и значениями float (суммы дивидендов)
        """
        logger.info(f"Загрузка дивидендов для {ticker} за период {start} - {end}")

        try:
            # Получаем сырые данные от Yahoo
            ticker_obj = self._get_ticker(ticker)
            raw_dividends = ticker_obj.dividends

            if raw_dividends.empty:
                logger.info(f"Нет данных о дивидендах для {ticker}")
                return pd.Series(dtype=float)

            # Фильтруем по периоду
            mask = (raw_dividends.index >= start) & (raw_dividends.index <= end)
            filtered = raw_dividends[mask]

            # Приводим к единому формату
            result = filtered.astype(float)
            result = self._ensure_datetime_index(result.to_frame())[result.name]

            logger.info(f"Загружено {len(result)} записей о дивидендах для {ticker}")
            return result

        except Exception as e:
            logger.error(f"Ошибка загрузки дивидендов для {ticker}: {e}")
            raise

    def get_splits(self, ticker: str, start: str, end: str) -> pd.Series:
        """
        Получение истории сплитов из Yahoo Finance.

        Parameters
        ----------
        ticker : str
            Тикер инструмента
        start : str
            Начальная дата в формате 'YYYY-MM-DD'
        end : str
            Конечная дата в формате 'YYYY-MM-DD'

        Returns
        -------
        pd.Series
            Series с индексом DatetimeIndex (даты сплитов) и значениями float (коэффициенты)
        """
        logger.info(f"Загрузка сплитов для {ticker} за период {start} - {end}")

        try:
            # Получаем сырые данные от Yahoo
            ticker_obj = self._get_ticker(ticker)
            raw_splits = ticker_obj.splits

            if raw_splits.empty:
                logger.info(f"Нет данных о сплитах для {ticker}")
                return pd.Series(dtype=float)

            # Фильтруем по периоду
            mask = (raw_splits.index >= start) & (raw_splits.index <= end)
            filtered = raw_splits[mask]

            # Приводим к единому формату
            result = filtered.astype(float)
            result = self._ensure_datetime_index(result.to_frame())[result.name]

            logger.info(f"Загружено {len(result)} записей о сплитах для {ticker}")
            return result

        except Exception as e:
            logger.error(f"Ошибка загрузки сплитов для {ticker}: {e}")
            raise

    def validate_ticker(self, ticker: str) -> bool:
        """
        Проверка существования тикера в Yahoo Finance.

        Parameters
        ----------
        ticker : str
            Тикер для проверки

        Returns
        -------
        bool
            True если тикер существует, False если нет
        """
        try:
            # Пробуем получить информацию о тикере
            ticker_obj = self._get_ticker(ticker)
            info = ticker_obj.info

            # Если info не пустой и содержит символ - тикер валидный
            return bool(info and info.get('symbol', '').upper() == ticker.upper())

        except Exception as e:
            logger.debug(f"Тикер {ticker} не найден в Yahoo Finance: {e}")
            return False