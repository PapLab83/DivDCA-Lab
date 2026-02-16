"""
Фетчер для получения сплитов акций.
Сплиты всегда сохраняются с фактическими датами событий, без агрегации по периодам.
"""

from typing import List, Dict, Any, Optional
import pandas as pd

from .base_fetcher import BaseFetcher
from .providers import DataProvider


class SplitFetcher(BaseFetcher):
    """
    Фетчер для сплитов акций.

    В отличие от цен и дивидендов, сплиты не агрегируются по периодам,
    а сохраняются с фактическими датами событий. Это важно для корректного
    пересчета цен и дивидендов при обратных сплитах.

    Формат выходных данных:
    - date: дата сплита в формате YYYY-MM-DD
    - year: год
    - split_ratio: коэффициент сплита (2.0 = 2-к-1, 0.5 = 1-к-2)
    - split_type: человекочитаемое описание ("2-for-1", "1-for-2")
    """

    def __init__(
            self,
            ticker: str,
            start_date: str,
            end_date: str,
            frequency: str = 'YE',
            provider: Optional[DataProvider] = None,
            include_description: bool = True,
            **kwargs
    ):
        """
        Инициализация фетчера сплитов.

        Parameters
        ----------
        ticker : str
            Тикер инструмента
        start_date : str
            Начальная дата в формате 'YYYY-MM-DD'
        end_date : str
            Конечная дата в формате 'YYYY-MM-DD'
        provider : DataProvider, optional
            Провайдер данных
        include_description : bool
            Добавлять ли человекочитаемое описание сплита
        **kwargs
            Дополнительные параметры для базового класса
        """
        super().__init__(ticker, start_date, end_date, frequency=frequency, provider=provider, **kwargs)

        self.include_description = include_description
        self.logger.info(f"Фетчер сплитов инициализирован (include_description={include_description})")

    def fetch(self) -> List[Dict[str, Any]]:
        """
        Получение сплитов за указанный период.

        Returns
        -------
        List[Dict[str, Any]]
            Список записей с полями date, year, split_ratio, (split_type)
        """
        self.logger.info(f"Начало загрузки сплитов для {self.ticker}")

        # 1. Получаем сырые данные от провайдера
        raw_splits = self.provider.get_splits(
            ticker=self.ticker,
            start=self.start_date,
            end=self.end_date
        )

        if raw_splits.empty:
            self.logger.info(f"Нет данных о сплитах для {self.ticker} за указанный период")
            return []

        self.logger.info(f"Получено {len(raw_splits)} записей о сплитах")

        # 2. Преобразуем в список словарей
        records = []
        for date, ratio in raw_splits.items():
            record = {
                'date': date.strftime('%Y-%m-%d'),
                'year': date.year,
                'split_ratio': float(ratio)
            }

            # Добавляем человекочитаемое описание если нужно
            if self.include_description:
                record['split_type'] = self._format_split_description(ratio)

            records.append(record)

        # 3. Сортируем по дате
        records.sort(key=lambda x: x['date'])

        # Логируем информацию о сплитах
        self._log_splits_summary(records)

        return records

    def _format_split_description(self, ratio: float) -> str:
        """
        Преобразует коэффициент сплита в человекочитаемый формат.

        Parameters
        ----------
        ratio : float
            Коэффициент сплита (2.0, 0.5 и т.д.)

        Returns
        -------
        str
            Описание типа сплита ("2-for-1", "1-for-2", "reverse split 1-for-2")
        """
        if ratio > 1:
            # Обычный сплит (например, 2-к-1)
            return f"{int(ratio)}-for-1"
        elif ratio < 1:
            # Обратный сплит (например, 1-к-2)
            reverse_ratio = int(1 / ratio)
            return f"1-for-{reverse_ratio} (reverse split)"
        else:
            return "no split"

    def _log_splits_summary(self, records: List[Dict]) -> None:
        """
        Логирует сводку по сплитам.

        Parameters
        ----------
        records : List[Dict]
            Список записей о сплитах
        """
        if not records:
            self.logger.info(f"Сплиты для {self.ticker} не найдены")
            return

        # Группируем по типу
        forward_splits = [r for r in records if r['split_ratio'] > 1]
        reverse_splits = [r for r in records if r['split_ratio'] < 1]

        summary = []
        if forward_splits:
            summary.append(f"обычных: {len(forward_splits)}")
        if reverse_splits:
            summary.append(f"обратных: {len(reverse_splits)}")

        self.logger.info(
            f"Найдено сплитов для {self.ticker}: {len(records)} "
            f"({', '.join(summary)})"
        )

        # Показываем первые несколько
        if len(records) <= 5:
            for r in records:
                self.logger.info(
                    f"  {r['date']}: {r.get('split_type', r['split_ratio'])}"
                )
        else:
            self.logger.info(f"  Первый: {records[0]['date']}")
            self.logger.info(f"  Последний: {records[-1]['date']}")

    def get_split_factor(self, as_of_date: str) -> float:
        """
        Возвращает кумулятивный фактор сплита на указанную дату.
        Полезно для пересчета исторических цен.

        Parameters
        ----------
        as_of_date : str
            Дата в формате 'YYYY-MM-DD'

        Returns
        -------
        float
            Произведение всех сплитов до указанной даты
        """
        # Получаем все сплиты
        all_splits = self.provider.get_splits(
            ticker=self.ticker,
            start=self.start_date,
            end=as_of_date
        )

        if all_splits.empty:
            return 1.0

        # Перемножаем все коэффициенты сплитов
        return float(all_splits.product())

    def get_split_history(self) -> pd.DataFrame:
        """
        Возвращает историю сплитов в виде DataFrame для анализа.

        Returns
        -------
        pd.DataFrame
            DataFrame с колонками date, ratio, cumulative_factor
        """
        raw_splits = self.provider.get_splits(
            ticker=self.ticker,
            start=self.start_date,
            end=self.end_date
        )

        if raw_splits.empty:
            return pd.DataFrame(columns=['date', 'ratio', 'cumulative_factor'])

        # Создаем DataFrame
        df = pd.DataFrame({
            'date': raw_splits.index,
            'ratio': raw_splits.values
        })

        # Добавляем кумулятивный фактор
        df['cumulative_factor'] = df['ratio'].cumprod()

        return df

    def _get_filename(self) -> str:
        """
        Возвращает имя файла для сохранения сплитов.

        Returns
        -------
        str
            Имя файла в формате 'splits_TICKER.jsonl'
        """
        return f"splits_{self.ticker}.jsonl"


# Удобная функция для быстрого получения сплитов
def fetch_splits(
        ticker: str,
        start_date: str,
        end_date: str,
        include_description: bool = True,
        **kwargs
) -> List[Dict[str, Any]]:
    """
    Быстрое получение сплитов.

    Parameters
    ----------
    ticker : str
        Тикер инструмента
    start_date : str
        Начальная дата
    end_date : str
        Конечная дата
    include_description : bool
        Добавлять ли человекочитаемое описание

    Returns
    -------
    List[Dict[str, Any]]
        Список записей о сплитах
    """
    fetcher = SplitFetcher(
        ticker,
        start_date,
        end_date,
        include_description=include_description,
        **kwargs
    )
    return fetcher.fetch()


# Функция для получения кумулятивного фактора
def get_cumulative_split_factor(
        ticker: str,
        as_of_date: str,
        start_date: str = "1900-01-01",
        **kwargs
) -> float:
    """
    Получение кумулятивного фактора сплита на указанную дату.

    Parameters
    ----------
    ticker : str
        Тикер инструмента
    as_of_date : str
        Дата, на которую нужен фактор
    start_date : str
        Начальная дата для поиска сплитов

    Returns
    -------
    float
        Кумулятивный фактор сплита
    """
    fetcher = SplitFetcher(ticker, start_date, as_of_date, **kwargs)
    return fetcher.get_split_factor(as_of_date)