"""
Базовый класс для всех фетчеров.
Содержит общую логику: работа с провайдером, логирование, сохранение в JSONL.
"""

from abc import ABC, abstractmethod
from pathlib import Path
import logging
import json
from typing import List, Dict, Any, Optional
import pandas as pd

from config.config import ETL_OUTPUT_DATA_DIR
from .providers import get_provider, DataProvider, DataSource


class BaseFetcher(ABC):
    """
    Абстрактный базовый класс для всех фетчеров.

    Предоставляет общую функциональность:
    - Работа с провайдером данных
    - Логирование
    - Сохранение результатов в JSONL
    - Генерацию дат

    Конкретные фетчеры наследуют этот класс и реализуют метод fetch().
    """

    def __init__(
            self,
            ticker: str,
            start_date: str,
            end_date: str,
            frequency: str = 'YE',
            provider: Optional[DataProvider] = None,
            data_source: DataSource = DataSource.YAHOO,
            output_dir: Path = ETL_OUTPUT_DATA_DIR,
    ):
        """
        Инициализация базового фетчера.

        Parameters
        ----------
        ticker : str
            Тикер инструмента
        start_date : str
            Начальная дата в формате 'YYYY-MM-DD'
        end_date : str
            Конечная дата в формате 'YYYY-MM-DD'
        provider : DataProvider, optional
            Провайдер данных (если не указан, создается из data_source)
        data_source : DataSource
            Источник данных для создания провайдера (по умолчанию YAHOO)
        output_dir : Path
            Директория для сохранения результатов
        """
        self.ticker = ticker.upper()
        self.start_date = start_date
        self.end_date = end_date

        # Провайдер данных (если не передан - создаем из источника)
        self.provider = provider or get_provider(data_source)

        # Директория для выходных файлов
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Настройка логгера
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._setup_logging()

        self.logger.info(f"Инициализирован {self.__class__.__name__} для {self.ticker}")

    def _setup_logging(self) -> None:
        """Настройка форматирования логов (если нужно дополнительно к корневой конфигурации)."""
        # Базовый logging уже настроен в orchestrator.py,
        # здесь можно добавить специфичные для фетчера хендлеры при необходимости
        pass

    def _generate_date_range(self) -> List[str]:
        """
        Генерирует список всех дат в заданном диапазоне.

        Returns
        -------
        List[str]
            Список дат в формате 'YYYY-MM-DD'
        """
        date_range = pd.date_range(start=self.start_date, end=self.end_date, freq='D')
        return [d.strftime('%Y-%m-%d') for d in date_range]

    def _save_to_jsonl(self, data: List[Dict] or pd.DataFrame, filename: str) -> Path:
        """
        Сохраняет данные в JSONL формате.

        Parameters
        ----------
        data : List[Dict] or pd.DataFrame
            Данные для сохранения
        filename : str
            Имя файла (например, 'prices_JPM.jsonl')

        Returns
        -------
        Path
            Путь к сохраненному файлу
        """
        filepath = self.output_dir / filename

        # Преобразуем DataFrame в список словарей если нужно
        if isinstance(data, pd.DataFrame):
            # Для DataFrame сбрасываем индекс в колонку, если это даты
            if isinstance(data.index, pd.DatetimeIndex):
                data = data.reset_index()
                data = data.rename(columns={'index': 'date'})
            records = data.to_dict(orient='records')
        else:
            records = data

        # Сохраняем в JSONL (по одному JSON объекту на строку)
        with open(filepath, 'w', encoding='utf-8') as f:
            for record in records:
                # Конвертируем date в строку если это Timestamp
                if 'date' in record and hasattr(record['date'], 'strftime'):
                    record['date'] = record['date'].strftime('%Y-%m-%d')

                # Добавляем год для удобства
                if 'date' in record and 'year' not in record:
                    record['year'] = int(record['date'][:4])

                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        self.logger.info(f"Сохранено {len(records)} записей в {filepath}")
        return filepath

    def _validate_period(self) -> bool:
        """
        Проверяет корректность заданного периода.

        Returns
        -------
        bool
            True если период корректен
        """
        start = pd.to_datetime(self.start_date)
        end = pd.to_datetime(self.end_date)

        if start > end:
            self.logger.error(f"Начальная дата {self.start_date} позже конечной {self.end_date}")
            return False

        if start.year < 1900:
            self.logger.warning(f"Начальная дата {self.start_date} очень ранняя, возможны проблемы с данными")

        return True

    @abstractmethod
    def fetch(self) -> List[Dict[str, Any]]:
        """
        Основной метод получения и обработки данных.
        Должен быть реализован в каждом конкретном фетчере.

        Returns
        -------
        List[Dict[str, Any]]
            Список записей с данными
        """
        pass

    def run(self) -> Path:
        """
        Запускает процесс получения данных и возвращает путь к сохраненному файлу.

        Returns
        -------
        Path
            Путь к файлу с результатами
        """
        self.logger.info(f"Запуск получения данных для {self.ticker}")

        if not self._validate_period():
            raise ValueError(f"Некорректный период: {self.start_date} - {self.end_date}")

        # Получаем данные
        data = self.fetch()

        # Генерируем имя файла (должно быть переопределено в наследниках или передано)
        filename = self._get_filename()

        # Сохраняем
        return self._save_to_jsonl(data, filename)

    def _get_filename(self) -> str:
        """
        Возвращает имя файла для сохранения.
        Должен быть переопределен в наследниках.

        Returns
        -------
        str
            Имя файла
        """
        return f"data_{self.ticker}.jsonl"