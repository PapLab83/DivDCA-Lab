"""
Базовый абстрактный класс для всех провайдеров данных.
Определяет контракт, который обязан выполнить каждый провайдер.
"""

from abc import ABC, abstractmethod
import pandas as pd


class DataProvider(ABC):
    """
    Абстрактный базовый класс для провайдеров финансовых данных.

    Все конкретные провайдеры (Yahoo, Alpha Vantage и т.д.) должны наследовать этот класс
    и реализовывать все абстрактные методы, приводя данные к единому формату.
    """

    @abstractmethod
    def get_prices(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """
        Получение исторических цен актива.

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
            DataFrame с индексом DatetimeIndex и колонками:
            - 'Open'   : float - цена открытия
            - 'High'   : float - максимальная цена
            - 'Low'    : float - минимальная цена
            - 'Close'  : float - цена закрытия
            - 'Volume' : float - объем торгов

            Индекс должен содержать все даты в диапазоне (без пропусков),
            пропущенные значения должны быть заполнены методом forward fill.
        """
        pass

    @abstractmethod
    def get_dividends(self, ticker: str, start: str, end: str) -> pd.Series:
        """
        Получение истории дивидендных выплат.

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
            Series с индексом DatetimeIndex (даты выплат) и значениями float (суммы дивидендов).
            Индекс содержит только даты фактических выплат (возможны пропуски).
        """
        pass

    @abstractmethod
    def get_splits(self, ticker: str, start: str, end: str) -> pd.Series:
        """
        Получение истории сплитов акций.

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
            Series с индексом DatetimeIndex (даты сплитов) и значениями float (коэффициент сплита).
            Например: 2.0 для сплита 2-к-1, 0.5 для обратного сплита 1-к-2.
            Индекс содержит только даты событий (возможны пропуски).
        """
        pass

    @abstractmethod
    def validate_ticker(self, ticker: str) -> bool:
        """
        Проверка существования тикера в источнике данных.

        Parameters
        ----------
        ticker : str
            Тикер для проверки

        Returns
        -------
        bool
            True если тикер существует, False если нет
        """
        pass

    def _ensure_datetime_index(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Вспомогательный метод: гарантирует, что индекс является DatetimeIndex.

        Parameters
        ----------
        data : pd.DataFrame
            DataFrame с индексом, который может быть строковым или datetime

        Returns
        -------
        pd.DataFrame
            DataFrame с гарантированным DatetimeIndex
        """
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        return data

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
        return data.reindex(full_range).fillna(method='ffill')