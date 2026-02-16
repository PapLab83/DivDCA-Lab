"""
Фетчер для получения цен закрытия акций.
Берет сырые данные от провайдера и преобразует их в формат для расчетов.
"""

from typing import List, Dict, Any, Optional
import pandas as pd

from .base_fetcher import BaseFetcher
from .providers import DataProvider


class PriceFetcher(BaseFetcher):
    """
    Фетчер для цен закрытия акций.

    Получает исторические цены от провайдера и преобразует их в формат:
    - date: дата в формате YYYY-MM-DD (конец периода)
    - year: год
    - price: цена закрытия на конец периода

    Поддерживает различные частоты: годовые, месячные, дневные.
    """

    def __init__(
            self,
            ticker: str,
            start_date: str,
            end_date: str,
            frequency: str = 'YE',
            provider: Optional[DataProvider] = None,
            **kwargs
    ):
        """
        Инициализация фетчера цен.

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
            - 'YE' - годовая (последний день года)
            - 'QE' - квартальная (последний день квартала)
            - 'ME' - месячная (последний день месяца)
            - 'DE' - дневная (все даты)
        provider : DataProvider, optional
            Провайдер данных
        **kwargs
            Дополнительные параметры для базового класса
        """
        super().__init__(ticker, start_date, end_date, provider, **kwargs)

        self.frequency = frequency
        self.logger.info(f"Частота данных: {frequency}")

    def fetch(self) -> List[Dict[str, Any]]:
        """
        Получение и обработка цен закрытия.

        Returns
        -------
        List[Dict[str, Any]]
            Список записей с полями date, year, price
        """
        self.logger.info(f"Начало загрузки цен для {self.ticker}")

        # 1. Получаем сырые данные от провайдера
        raw_data = self.provider.get_prices(
            ticker=self.ticker,
            start=self.start_date,
            end=self.end_date
        )

        if raw_data.empty:
            self.logger.warning(f"Нет данных о ценах для {self.ticker}")
            return []

        self.logger.info(f"Получено {len(raw_data)} сырых записей от провайдера")

        # 2. Агрегируем до нужной частоты
        if self.frequency != 'D':
            # Для не-дневных данных берем последнее значение в периоде
            aggregated = raw_data.resample(self.frequency).last()
            self.logger.info(f"После агрегации ({self.frequency}): {len(aggregated)} записей")
        else:
            aggregated = raw_data.copy()

        # 3. Оставляем только цену закрытия
        result = aggregated[['Close']].copy()
        result = result.rename(columns={'Close': 'price'})

        # 4. Преобразуем в список словарей
        records = []
        for date, row in result.iterrows():
            records.append({
                'date': date.strftime('%Y-%m-%d'),
                'year': date.year,
                'price': float(row['price'])
            })

        self.logger.info(f"Подготовлено {len(records)} записей для сохранения")

        # Проверяем наличие пропусков
        self._check_data_gaps(records)

        return records

    def _check_data_gaps(self, records: List[Dict]) -> None:
        """
        Проверяет наличие пропусков в данных и логирует предупреждения.

        Parameters
        ----------
        records : List[Dict]
            Список записей с данными
        """
        if len(records) == 0:
            return

        # Ожидаемое количество записей исходя из частоты
        if self.frequency == 'YE':
            expected = pd.date_range(self.start_date, self.end_date, freq='YE').shape[0]
        elif self.frequency == 'QE':
            expected = pd.date_range(self.start_date, self.end_date, freq='QE').shape[0]
        elif self.frequency == 'ME':
            expected = pd.date_range(self.start_date, self.end_date, freq='ME').shape[0]
        else:  # 'D'
            expected = pd.date_range(self.start_date, self.end_date, freq='D').shape[0]

        if len(records) < expected:
            missing = expected - len(records)
            self.logger.warning(
                f"Обнаружены пропуски в данных: ожидалось {expected}, получено {len(records)} "
                f"(пропущено {missing} записей)"
            )

            # Находим конкретные пропущенные годы/даты
            existing_dates = {r['date'] for r in records}
            all_dates = pd.date_range(self.start_date, self.end_date, freq=self.frequency)
            missing_dates = [d for d in all_dates if d.strftime('%Y-%m-%d') not in existing_dates]

            if missing_dates and len(missing_dates) <= 5:  # Показываем только если не слишком много
                self.logger.warning(f"Пропущенные даты: {[d.strftime('%Y-%m-%d') for d in missing_dates]}")

    def _get_filename(self) -> str:
        """
        Возвращает имя файла для сохранения цен.

        Returns
        -------
        str
            Имя файла в формате 'prices_TICKER.jsonl'
        """
        return f"prices_{self.ticker}.jsonl"


# Для обратной совместимости и удобства импорта
def fetch_prices(
        ticker: str,
        start_date: str,
        end_date: str,
        frequency: str = 'YE',
        **kwargs
) -> List[Dict[str, Any]]:
    """
    Удобная функция для быстрого получения цен.

    Parameters
    ----------
    ticker : str
        Тикер инструмента
    start_date : str
        Начальная дата
    end_date : str
        Конечная дата
    frequency : str
        Частота данных

    Returns
    -------
    List[Dict[str, Any]]
        Список записей с ценами
    """
    fetcher = PriceFetcher(ticker, start_date, end_date, frequency, **kwargs)
    return fetcher.fetch()