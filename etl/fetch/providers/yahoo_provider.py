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
        logger.info(f"Загрузка цен для {ticker} за период {start} - {end}")

        try:
            ticker_obj = self._get_ticker(ticker)
            raw_data = ticker_obj.history(start=start, end=end)

            if raw_data.empty:
                logger.warning(f"Нет данных о ценах для {ticker} за указанный период")
                return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

            # Убираем таймзону из индекса
            if raw_data.index.tz is not None:
                raw_data.index = raw_data.index.tz_localize(None)

            result = pd.DataFrame(index=raw_data.index)
            result['Open'] = raw_data['Open'].astype(float)
            result['High'] = raw_data['High'].astype(float)
            result['Low'] = raw_data['Low'].astype(float)
            result['Close'] = raw_data['Close'].astype(float)
            result['Volume'] = raw_data['Volume'].astype(float)

            result = self._ensure_datetime_index(result)
            result = self._fill_missing_dates(result, freq='D')

            logger.info(f"Загружено {len(result)} записей о ценах для {ticker}")
            return result

        except Exception as e:
            logger.error(f"Ошибка загрузки цен для {ticker}: {e}")
            raise

    def get_dividends(self, ticker: str, start: str, end: str) -> pd.Series:
        logger.info(f"Загрузка дивидендов для {ticker} за период {start} - {end}")

        try:
            ticker_obj = self._get_ticker(ticker)
            raw_dividends = ticker_obj.dividends

            if raw_dividends.empty:
                logger.info(f"Нет данных о дивидендах для {ticker}")
                return pd.Series(dtype=float)

            # Убираем таймзону из индекса
            if raw_dividends.index.tz is not None:
                raw_dividends.index = raw_dividends.index.tz_localize(None)

            # Фильтруем по периоду
            start_ts = pd.Timestamp(start)
            end_ts = pd.Timestamp(end)
            mask = (raw_dividends.index >= start_ts) & (raw_dividends.index <= end_ts)
            filtered = raw_dividends[mask]

            result = filtered.astype(float)

            logger.info(f"Загружено {len(result)} записей о дивидендах для {ticker}")
            return result

        except Exception as e:
            logger.error(f"Ошибка загрузки дивидендов для {ticker}: {e}")
            raise

    def get_splits(self, ticker: str, start: str, end: str) -> pd.Series:
        logger.info(f"Загрузка сплитов для {ticker} за период {start} - {end}")

        try:
            ticker_obj = self._get_ticker(ticker)
            raw_splits = ticker_obj.splits

            if raw_splits.empty:
                logger.info(f"Нет данных о сплитах для {ticker}")
                return pd.Series(dtype=float)

            # Убираем таймзону из индекса
            if raw_splits.index.tz is not None:
                raw_splits.index = raw_splits.index.tz_localize(None)

            # Фильтруем по периоду
            start_ts = pd.Timestamp(start)
            end_ts = pd.Timestamp(end)
            mask = (raw_splits.index >= start_ts) & (raw_splits.index <= end_ts)
            filtered = raw_splits[mask]

            result = filtered.astype(float)

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

    def _fill_missing_dates(self, data: pd.DataFrame, freq: str = 'D') -> pd.DataFrame:
        """
        Вспомогательный метод: заполняет пропущенные даты forward fill'ом.

        Parameters
        ----------
        data : pd.DataFrame
            DataFrame с DatetimeIndex
        freq : str
            Частота передискретизации ('D' - дневная, 'B' - рабочие дни и т.д.)

        Returns
        -------
        pd.DataFrame
            DataFrame с непрерывным индексом дат
        """
        # Создаем полный диапазон дат
        full_range = pd.date_range(start=data.index.min(),
                                   end=data.index.max(),
                                   freq=freq)

        # Переиндексируем и заполняем пропуски
        # Исправление: убираем method, используем ffill()
        return data.reindex(full_range).ffill()