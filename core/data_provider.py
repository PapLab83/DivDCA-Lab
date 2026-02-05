"""
Модуль для загрузки исторических данных из локальных JSONL-файлов.
"""
import json
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
from pandas import DataFrame

from core.config import get_data_path, TICKER, START_YEAR, END_YEAR


class LocalJsonDataProvider:
    """
    Загружает исторические данные по акциям из JSONL-файлов.
    Каждая строка файла должна быть JSON-объектом с полями:
    date (str), price (float), div_annual (float),
    reason_short (str, опционально), reason_long (str, опционально).
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Инициализация провайдера данных.

        Parameters
        ----------
        data_dir : Path, optional
            Директория с JSONL-файлами. Если не указана, используется путь из config.
        """
        self.data_dir = data_dir or get_data_path().parent

    def load_ticker_data(self, ticker: str = TICKER) -> DataFrame:
        """
        Загружает данные для указанного тикера из JSONL-файла.

        Parameters
        ----------
        ticker : str
            Тикер компании (например, 'JNJ').

        Returns
        -------
        DataFrame
            DataFrame с колонками:
            - date (datetime)
            - price (float)
            - div_annual (float)
            - reason_short (str, может содержать NaN)
            - reason_long (str, может содержать NaN)

        Raises
        ------
        FileNotFoundError
            Если файл с данными не найден.
        ValueError
            Если файл пустой или имеет неверный формат.
        """
        file_path = self.data_dir / f"{ticker.upper()}.jsonl"

        if not file_path.exists():
            raise FileNotFoundError(f"Файл с данными не найден: {file_path}")

        data = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        data.append(record)
                    except json.JSONDecodeError as e:
                        raise ValueError(
                            f"Ошибка JSON в строке {line_num} файла {file_path}: {e}"
                        ) from e
        except IOError as e:
            raise ValueError(f"Ошибка чтения файла {file_path}: {e}") from e

        if not data:
            raise ValueError(f"Файл {file_path} пустой или не содержит валидных данных.")

        # Конвертируем в DataFrame
        df = pd.DataFrame(data)

        # Проверяем наличие обязательных колонок
        required_columns = {'date', 'price', 'div_annual'}
        if not required_columns.issubset(df.columns):
            missing = required_columns - set(df.columns)
            raise ValueError(
                f"В файле {file_path} отсутствуют обязательные колонки: {missing}"
            )

        # Преобразуем дату
        df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='coerce')
        if df['date'].isna().any():
            raise ValueError(
                f"В файле {file_path} есть некорректные даты. "
                f"Ожидается формат YYYY-MM-DD."
            )

        # Сортируем по дате
        df = df.sort_values('date').reset_index(drop=True)

        # Преобразуем числовые колонки
        numeric_columns = ['price', 'div_annual']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].isna().any():
                raise ValueError(
                    f"В файле {file_path} есть некорректные числовые значения в колонке '{col}'."
                )

        # Добавляем год для удобства фильтрации
        df['year'] = df['date'].dt.year

        # Опциональные колонки
        optional_columns = ['reason_short', 'reason_long']
        for col in optional_columns:
            if col not in df.columns:
                df[col] = None

        # Выбираем и упорядочиваем колонки
        columns_order = ['date', 'year', 'price', 'div_annual', 'reason_short', 'reason_long']
        df = df[columns_order]

        return df

    def load_data_for_period(
            self,
            ticker: str = TICKER,
            start_year: int = START_YEAR,
            end_year: int = END_YEAR
    ) -> DataFrame:
        """
        Загружает данные для указанного тикера и фильтрует по заданному периоду.

        Parameters
        ----------
        ticker : str
            Тикер компании.
        start_year : int
            Начальный год периода.
        end_year : int
            Конечный год периода.

        Returns
        -------
        DataFrame
            Отфильтрованный DataFrame за указанный период.

        Raises
        ------
        ValueError
            Если запрошенный период выходит за пределы доступных данных.
        """
        df = self.load_ticker_data(ticker)

        # Проверяем доступный диапазон
        min_year = df['year'].min()
        max_year = df['year'].max()

        if start_year < min_year or end_year > max_year:
            raise ValueError(
                f"Запрошенный период ({start_year}-{end_year}) выходит за пределы "
                f"доступных данных ({min_year}-{max_year}) для тикера {ticker}."
            )

        # Фильтруем по периоду
        mask = (df['year'] >= start_year) & (df['year'] <= end_year)
        filtered_df = df[mask].copy()

        if filtered_df.empty:
            raise ValueError(
                f"Нет данных для тикера {ticker} в периоде {start_year}-{end_year}."
            )

        return filtered_df


# Синглтон-экземпляр для удобства
_data_provider_instance: Optional[LocalJsonDataProvider] = None


def get_data_provider() -> LocalJsonDataProvider:
    """
    Возвращает глобальный экземпляр провайдера данных (синглтон).

    Returns
    -------
    LocalJsonDataProvider
        Экземпляр провайдера данных.
    """
    global _data_provider_instance
    if _data_provider_instance is None:
        _data_provider_instance = LocalJsonDataProvider()
    return _data_provider_instance


if __name__ == "__main__":
    # Простой тест загрузки
    try:
        provider = LocalJsonDataProvider()
        data = provider.load_ticker_data("JNJ")
        print(f"✅ Данные успешно загружены. Записей: {len(data)}")
        print(f"Доступный период: {data['year'].min()} - {data['year'].max()}")
        print("\nПервые 3 записи:")
        print(data.head(3).to_string())

        # Тест фильтрации по периоду
        filtered = provider.load_data_for_period("JNJ", START_YEAR, END_YEAR)
        print(f"\n✅ Данные за {START_YEAR}-{END_YEAR}. Записей: {len(filtered)}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()