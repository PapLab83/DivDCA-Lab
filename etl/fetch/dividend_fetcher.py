"""
Фетчер для получения дивидендов по акциям.
Берет сырые данные от провайдера и агрегирует их по периодам.
"""

from typing import List, Dict, Any, Optional
import pandas as pd

from .base_fetcher import BaseFetcher
from .providers import DataProvider


class DividendFetcher(BaseFetcher):
    """
    Фетчер для дивидендных выплат.

    Получает историю дивидендов от провайдера и агрегирует по периодам.
    Поддерживает различные частоты агрегации: годовая, квартальная, месячная.

    Формат выходных данных:
    - date: дата в формате YYYY-MM-DD (конец периода агрегации)
    - year: год
    - dividend: сумма дивидендов за период
    """

    def __init__(
            self,
            ticker: str,
            start_date: str,
            end_date: str,
            frequency: str = 'YE',
            aggregation: str = 'sum',
            provider: Optional[DataProvider] = None,
            **kwargs
    ):
        """
        Инициализация фетчера дивидендов.

        Parameters
        ----------
        ticker : str
            Тикер инструмента
        start_date : str
            Начальная дата в формате 'YYYY-MM-DD'
        end_date : str
            Конечная дата в формате 'YYYY-MM-DD'
        frequency : str
            Частота агрегации:
            - 'YE' - годовая
            - 'QE' - квартальная
            - 'ME' - месячная
        aggregation : str
            Метод агрегации:
            - 'sum' - сумма за период
            - 'count' - количество выплат
            - 'mean' - средний дивиденд
        provider : DataProvider, optional
            Провайдер данных
        **kwargs
            Дополнительные параметры для базового класса
        """
        super().__init__(ticker, start_date, end_date, provider, **kwargs)

        self.frequency = frequency
        self.aggregation = aggregation

        self.logger.info(f"Частота агрегации: {frequency}, метод: {aggregation}")

    def fetch(self) -> List[Dict[str, Any]]:
        """
        Получение и агрегация дивидендов.

        Returns
        -------
        List[Dict[str, Any]]
            Список записей с полями date, year, dividend
        """
        self.logger.info(f"Начало загрузки дивидендов для {self.ticker}")

        # 1. Получаем сырые данные от провайдера
        raw_dividends = self.provider.get_dividends(
            ticker=self.ticker,
            start=self.start_date,
            end=self.end_date
        )

        if raw_dividends.empty:
            self.logger.info(f"Нет данных о дивидендах для {self.ticker} за указанный период")
            return []

        self.logger.info(f"Получено {len(raw_dividends)} сырых записей о дивидендах")

        # Показываем примеры выплат
        if len(raw_dividends) > 0:
            sample = raw_dividends.head(3)
            self.logger.debug(f"Примеры выплат: {sample.to_dict()}")

        # 2. Агрегируем по периодам
        aggregated = self._aggregate_dividends(raw_dividends)

        # 3. Преобразуем в список словарей
        records = []
        for date, value in aggregated.items():
            records.append({
                'date': date.strftime('%Y-%m-%d'),
                'year': date.year,
                'dividend': float(value)
            })

        self.logger.info(f"Подготовлено {len(records)} записей после агрегации")

        # Проверяем на наличие нулевых периодов
        self._check_zero_periods(records)

        return records

    def _aggregate_dividends(self, dividends: pd.Series) -> pd.Series:
        """
        Агрегирует дивиденды по периодам с заданной частотой.

        Parameters
        ----------
        dividends : pd.Series
            Series с дивидендами (индекс - даты выплат)

        Returns
        -------
        pd.Series
            Агрегированные дивиденды по периодам
        """
        if dividends.empty:
            return pd.Series(dtype=float)

        # Выбираем метод агрегации
        agg_methods = {
            'sum': 'sum',
            'count': 'count',
            'mean': 'mean'
        }

        method = agg_methods.get(self.aggregation, 'sum')

        # Агрегируем по периодам
        aggregated = dividends.resample(self.frequency).agg(method)

        # Заполняем NaN нулями (периоды без дивидендов)
        aggregated = aggregated.fillna(0)

        # Фильтруем только периоды в нашем диапазоне
        start = pd.to_datetime(self.start_date)
        end = pd.to_datetime(self.end_date)
        aggregated = aggregated[(aggregated.index >= start) & (aggregated.index <= end)]

        self.logger.info(
            f"Агрегация: {len(dividends)} выплат -> {len(aggregated)} периодов "
            f"(метод: {method})"
        )

        return aggregated

    def _check_zero_periods(self, records: List[Dict]) -> None:
        """
        Проверяет периоды с нулевыми дивидендами.

        Parameters
        ----------
        records : List[Dict]
            Список записей с дивидендами
        """
        zero_periods = [r for r in records if r['dividend'] == 0]

        if zero_periods:
            self.logger.info(
                f"Периодов без дивидендов: {len(zero_periods)} из {len(records)} "
                f"({len(zero_periods) / len(records) * 100:.1f}%)"
            )

            # Показываем первые несколько, если их не слишком много
            if len(zero_periods) <= 5:
                zero_dates = [r['date'] for r in zero_periods]
                self.logger.info(f"Периоды без дивидендов: {zero_dates}")

    def get_payment_dates(self) -> List[Dict[str, Any]]:
        """
        Возвращает фактические даты выплат (без агрегации).
        Полезно для детального анализа.

        Returns
        -------
        List[Dict[str, Any]]
            Список записей с фактическими выплатами
        """
        raw_dividends = self.provider.get_dividends(
            ticker=self.ticker,
            start=self.start_date,
            end=self.end_date
        )

        if raw_dividends.empty:
            return []

        records = []
        for date, amount in raw_dividends.items():
            records.append({
                'date': date.strftime('%Y-%m-%d'),
                'year': date.year,
                'dividend': float(amount),
                'payment_type': 'regular'  # Можно расширить для определения типа
            })

        return records

    def _get_filename(self) -> str:
        """
        Возвращает имя файла для сохранения дивидендов.

        Returns
        -------
        str
            Имя файла в формате 'dividends_TICKER.jsonl'
        """
        return f"dividends_{self.ticker}.jsonl"


# Удобная функция для быстрого получения дивидендов
def fetch_dividends(
        ticker: str,
        start_date: str,
        end_date: str,
        frequency: str = 'YE',
        aggregation: str = 'sum',
        **kwargs
) -> List[Dict[str, Any]]:
    """
    Быстрое получение агрегированных дивидендов.

    Parameters
    ----------
    ticker : str
        Тикер инструмента
    start_date : str
        Начальная дата
    end_date : str
        Конечная дата
    frequency : str
        Частота агрегации
    aggregation : str
        Метод агрегации

    Returns
    -------
    List[Dict[str, Any]]
        Список записей с дивидендами
    """
    fetcher = DividendFetcher(
        ticker, start_date, end_date,
        frequency=frequency,
        aggregation=aggregation,
        **kwargs
    )
    return fetcher.fetch()


# Дополнительная функция для получения всех выплат
def fetch_dividend_payments(
        ticker: str,
        start_date: str,
        end_date: str,
        **kwargs
) -> List[Dict[str, Any]]:
    """
    Получение всех фактических выплат дивидендов (без агрегации).

    Parameters
    ----------
    ticker : str
        Тикер инструмента
    start_date : str
        Начальная дата
    end_date : str
        Конечная дата

    Returns
    -------
    List[Dict[str, Any]]
        Список всех выплат с датами
    """
    fetcher = DividendFetcher(ticker, start_date, end_date, **kwargs)
    return fetcher.get_payment_dates()