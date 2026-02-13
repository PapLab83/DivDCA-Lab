"""
Модуль для экспорта результатов анализа в табличные форматы (CSV, Excel, JSON).
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
from pandas import DataFrame
import logging

from config.config import TABLES_DIR, generate_report_filename

logger = logging.getLogger(__name__)


class TableExporter:
    """
    Экспортёр табличных данных в различные форматы.
    Поддерживает CSV, Excel (.xlsx), JSON.
    """

    # Маппинг форматов на функции экспорта
    _EXPORT_METHODS = {
        'csv': '_export_to_csv',
        'xlsx': '_export_to_excel',
        'json': '_export_to_json'
    }

    def __init__(self, output_dir: Path = TABLES_DIR):
        """
        Инициализация экспортёра.

        Parameters
        ----------
        output_dir : Path
            Директория для сохранения файлов.
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_simulation_table(
            self,
            simulation_df: DataFrame,
            source_df: DataFrame,
            ticker: str,
            start_year: int,
            end_year: int,
            annual_investment: float,
            reinvest_div: bool,
            formats: list = None,
            export_final_report: bool = True
    ) -> Dict[str, Path]:
        """
        Экспортирует таблицу с детальными результатами симуляции.

        Parameters
        ----------
        simulation_df : DataFrame
            DataFrame с результатами симуляции.
        source_df: DataFrame,
            Исходные данные с reason_short, reason_long.
        ticker : str
            Тикер бумаги.
        start_year : int
            Год начала инвестирования.
        end_year : int
            Год окончания инвестирования.
        annual_investment : float
            Ежегодная сумма инвестиций.
        reinvest_div : bool
            Флаг реинвестирования дивидендов.
        formats : list, optional
            Список форматов для экспорта. По умолчанию ['xlsx', 'csv'].
        export_final_report: bool = True
            Если True, экспортирует финальный отчёт (18 колонок).
            Если False, экспортирует полную симуляцию.

        Returns
        -------
        Dict[str, Path]
            Словарь {формат: путь_к_файлу} созданных файлов.
        """

        # Экспортируем в указанные форматы
        exported_files = {}
        # 1. Экспортируем финальный отчёт если нужно
        if export_final_report and source_df is not None:
            try:
                final_df = self.format_final_report(simulation_df, source_df, ticker)

                base_name_final = generate_report_filename(
                    prefix='final_report',
                    ticker=ticker,
                    start_year=start_year,
                    end_year=end_year,
                    annual_investment=annual_investment,
                    reinvest_div=reinvest_div
                )

                # # Экспортируем финальный отчёт в запрошенные форматы
                file_path = self.output_dir / f"{base_name_final}.xlsx"
                final_df.to_excel(file_path, index=False)
                exported_files['final_xlsx'] = file_path
                logger.debug(f"Создан финальный Excel: {file_path}")

            except Exception as e:
                logger.warning(f"Не удалось создать финальный отчёт: {e}")

        logger.info(f"Экспортирована таблица симуляции: {len(exported_files)} файлов")
        return exported_files

    def export_summary_table(
            self,
            summary_metrics: Dict[str, Any],
            ticker: str,
            start_year: int,
            end_year: int,
            annual_investment: float,
            reinvest_div: bool,
            formats: list = None
    ) -> Dict[str, Path]:
        """
        Экспортирует сводные метрики симуляции.

        Parameters
        ----------
        summary_metrics : Dict[str, Any]
            Словарь с метриками.
        ticker : str
            Тикер бумаги.
        start_year : int
            Год начала инвестирования.
        end_year : int
            Год окончания инвестирования.
        annual_investment : float
            Ежегодная сумма инвестиций.
        reinvest_div : bool
            Флаг реинвестирования дивидендов.
        formats : list, optional
            Список форматов для экспорта. По умолчанию ['json', 'xlsx'].

        Returns
        -------
        Dict[str, Path]
            Словарь {формат: путь_к_файлу} созданных файлов.
        """
        if formats is None:
            formats = ['json', 'xlsx']

        # Генерируем базовое имя файла
        base_name = generate_report_filename(
            prefix='summary',
            ticker=ticker,
            start_year=start_year,
            end_year=end_year,
            annual_investment=annual_investment,
            reinvest_div=reinvest_div
        )

        # Экспортируем в указанные форматы
        exported_files = {}
        for fmt in formats:
            if fmt == 'json':
                file_path = self._export_summary_to_json(summary_metrics, base_name)
                exported_files[fmt] = file_path
            elif fmt == 'xlsx':
                file_path = self._export_summary_to_excel(summary_metrics, base_name)
                exported_files[fmt] = file_path
            else:
                logger.warning(f"Формат {fmt} не поддерживается для сводной таблицы.")

        logger.info(f"Экспортирована сводная таблица: {len(exported_files)} файлов")
        return exported_files

    def export_validation_report(
            self,
            validation_result: Dict[str, Any],
            ticker: str,
            start_year: int,
            end_year: int,
            annual_investment: float,
            reinvest_div: bool
    ) -> Path:
        """
        Экспортирует отчёт валидации в текстовый файл.

        Parameters
        ----------
        validation_result : Dict[str, Any]
            Результаты валидации.
        ticker : str
            Тикер бумаги.
        start_year : int
            Год начала инвестирования.
        end_year : int
            Год окончания инвестирования.
        annual_investment : float
            Ежегодная сумма инвестиций.
        reinvest_div : bool
            Флаг реинвестирования дивидендов.

        Returns
        -------
        Path
            Путь к созданному файлу.
        """
        base_name = generate_report_filename(
            prefix='validation',
            ticker=ticker,
            start_year=start_year,
            end_year=end_year,
            annual_investment=annual_investment,
            reinvest_div=reinvest_div
        )

        file_path = self.output_dir / f"{base_name}.txt"

        # Формируем содержимое отчёта
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append(f"ОТЧЁТ ВАЛИДАЦИИ ДАННЫХ")
        report_lines.append(f"Тикер: {ticker}")
        report_lines.append(f"Период: {start_year}-{end_year}")
        report_lines.append(f"Дата генерации: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 60)

        if 'report_text' in validation_result:
            report_lines.append(validation_result['report_text'])
        else:
            report_lines.append(f"Статус: {'ПРОЙДЕНА' if validation_result.get('is_valid', False) else 'НЕ ПРОЙДЕНА'}")
            if 'messages' in validation_result:
                report_lines.append("\nСообщения:")
                for msg in validation_result['messages']:
                    report_lines.append(f"  - {msg}")

        report_lines.append("\n" + "=" * 60)

        # Записываем в файл
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))

        logger.info(f"Экспортирован отчёт валидации: {file_path}")
        return file_path

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _prepare_simulation_df(self, df: DataFrame) -> DataFrame:
        """
        Подготавливает DataFrame симуляции для экспорта:
        - Выбирает и переименовывает колонки
        - Форматирует числа
        - Сортирует колонки

        Returns
        -------
        DataFrame
            Подготовленный DataFrame.
        """
        # Копируем, чтобы не менять исходный
        export_df = df.copy()

        # Определяем маппинг колонок для читаемого вывода
        column_mapping = {
            'year': 'Год',
            'price': 'Цена ($)',
            'yoy_change_pct': 'Изменение цены за год (%)',
            'div_annual': 'Дивиденды за год ($)',
            'shares_bought': 'Куплено акций в году',
            'total_shares': 'Накоплено акций всего',
            'total_invested': 'Всего вложено ($)',
            'portfolio_value': 'Стоимость портфеля ($)',
            'div_received': 'Дивиденды получено в году ($)',
            'total_div_received': 'Всего дивидендов получено ($)',
            'net_result': 'Чистый результат ($)',
            'avg_cost': 'Средняя цена входа ($)',
            'yield_on_cost': 'Доходность на成本 (%)',
            'cap_gain_pct': 'Прирост капитала (%)',
            'div_return_pct': 'Доходность от дивидендов (%)',
            'total_return_pct': 'Общая доходность (%)',
            'cagr_pct': 'CAGR портфеля (%)'
        }

        # Оставляем только существующие колонки
        existing_columns = [col for col in column_mapping.keys() if col in export_df.columns]
        export_df = export_df[existing_columns]

        # Переименовываем
        export_df = export_df.rename(columns=column_mapping)

        # Форматируем числа
        for col in export_df.columns:
            if '($)' in col or 'Цена' in col or 'цена' in col.lower():
                export_df[col] = export_df[col].round(2)
            elif '(%)' in col or 'Доходность' in col or 'CAGR' in col:
                export_df[col] = export_df[col].round(2)
            elif 'акций' in col:
                export_df[col] = export_df[col].round(4)

        return export_df

    def format_final_report(
            self,
            simulation_df: DataFrame,
            source_df: DataFrame,
            ticker: str
    ) -> DataFrame:
        """
        Форматирует финальный отчёт для пользователя с 18 колонками.

        Parameters
        ----------
        simulation_df : DataFrame
            DataFrame с результатами симуляции.
        source_df : DataFrame
            Исходный DataFrame с reason_short, reason_long.
        ticker : str
            Тикер для добавления названия компании.

        Returns
        -------
        DataFrame
            Отформатированный DataFrame с 18 колонками.
        """
        from config.config import COMPANY_NAMES

        # 1. Объединяем данные
        # Проверяем, что есть колонка year в обоих DataFrame
        if 'year' not in simulation_df.columns or 'year' not in source_df.columns:
            raise ValueError("Оба DataFrame должны содержать колонку 'year'")

        # Объединяем по году
        merged_df = pd.merge(
            simulation_df,
            source_df[['year', 'reason_short', 'reason_long']],
            on='year',
            how='left'
        )

        # 2. Добавляем ticker и name
        merged_df['ticker'] = ticker
        merged_df['name'] = COMPANY_NAMES.get(ticker, ticker)

        # 3. Определяем маппинг и порядок колонок
        column_mapping = {
            'ticker': 'ticker',
            'name': 'name',
            'year': 'date',  # Используем год как дату (int)
            'price': 'price',
            'yoy_change_pct': 'yoy_change',
            'div_annual': 'div_annual',
            'avg_cost': 'avg_cost',
            'yield_on_cost': 'yield_on_cost',
            'total_div_received': 'cum_div',  # cum_div = total_div_received
            'total_invested': 'total_invested',
            'portfolio_value': 'portfolio_value',
            'total_div_received': 'total_div_received',  # Дублируем для ясности
            'net_result': 'net_result',
            'reason_short': 'reason_short',
            'reason_long': 'reason_long'
        }

        # 4. Выбираем только нужные колонки (исключаем служебные)
        # Убираем: cap_gain_pct, div_return_pct, total_return_pct, cagr_pct
        columns_to_keep = [
            'ticker', 'name', 'year', 'price', 'yoy_change_pct',
            'div_annual', 'avg_cost', 'yield_on_cost', 'total_div_received', 'div_received',
            'total_invested', 'portfolio_value', 'net_result',
            'reason_short', 'reason_long'
        ]

        # Фильтруем существующие колонки
        existing_columns = [col for col in columns_to_keep if col in merged_df.columns]
        final_df = merged_df[existing_columns].copy()

        # 5. Переименовываем колонки
        final_df = final_df.rename(columns={
            'year': 'date',
            'yoy_change_pct': 'yoy_change',
            'total_div_received': 'cum_div',  # Накопленные дивиденды
            'div_received': 'total_div_received'  # Дивиденды за этот год
        })

        # # 6. Добавляем total_div_received как отдельную колонку (дублирование cum_div)
        # final_df['total_div_received'] = final_df['cum_div']

        # 7. Форматируем числа
        # Округляем денежные значения до 2 знаков
        money_columns = ['price', 'div_annual', 'avg_cost', 'total_invested',
                         'portfolio_value', 'cum_div', 'total_div_received', 'net_result']
        for col in money_columns:
            if col in final_df.columns:
                final_df[col] = final_df[col].round(2)

        # Округляем проценты до 2 знаков
        percent_columns = ['yoy_change', 'yield_on_cost']
        for col in percent_columns:
            if col in final_df.columns:
                final_df[col] = final_df[col].round(2)

        # 8. Устанавливаем порядок колонок (18 колонок)
        final_column_order = [
            'ticker', 'name', 'date', 'price', 'yoy_change', 'div_annual',
            'avg_cost', 'yield_on_cost', 'total_invested', 'portfolio_value',
            'total_div_received', 'cum_div', 'net_result',
            'reason_short', 'reason_long'
        ]

        # Оставляем только существующие колонки в нужном порядке
        final_df = final_df[[col for col in final_column_order if col in final_df.columns]]

        return final_df

    def _export_to_csv(self, df: DataFrame, base_name: str) -> Path:
        """Экспорт DataFrame в CSV."""
        file_path = self.output_dir / f"{base_name}.csv"
        df.to_csv(file_path, index=False, encoding='utf-8')
        logger.debug(f"Создан CSV файл: {file_path}")
        return file_path

    def _export_to_excel(self, df: DataFrame, base_name: str) -> Path:
        """Экспорт DataFrame в Excel с форматированием."""
        file_path = self.output_dir / f"{base_name}.xlsx"

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Simulation', index=False)

            # Автонастройка ширины колонок
            worksheet = writer.sheets['Simulation']
            for column in df:
                column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
                col_idx = df.columns.get_loc(column)
                worksheet.column_dimensions[chr(65 + col_idx)].width = min(column_width, 30)

        logger.debug(f"Создан Excel файл: {file_path}")
        return file_path

    def _export_to_json(self, df: DataFrame, base_name: str) -> Path:
        """Экспорт DataFrame в JSON."""
        file_path = self.output_dir / f"{base_name}.json"

        # Конвертируем в словарь с ориентацией records
        data = {
            'metadata': {
                'generated_at': pd.Timestamp.now().isoformat(),
                'records_count': len(df)
            },
            'data': df.to_dict(orient='records')
        }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.debug(f"Создан JSON файл: {file_path}")
        return file_path

    def _export_summary_to_json(self, summary: Dict[str, Any], base_name: str) -> Path:
        """Экспорт сводных метрик в JSON."""
        file_path = self.output_dir / f"{base_name}.json"

        # Добавляем метаданные
        enriched_summary = {
            'metadata': {
                'generated_at': pd.Timestamp.now().isoformat(),
                'file_type': 'summary_metrics'
            },
            'metrics': summary
        }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(enriched_summary, f, ensure_ascii=False, indent=2)

        logger.debug(f"Создан JSON файл сводных метрик: {file_path}")
        return file_path

    def _export_summary_to_excel(self, summary: Dict[str, Any], base_name: str) -> Path:
        """Экспорт сводных метрик в Excel."""
        file_path = self.output_dir / f"{base_name}.xlsx"

        # Преобразуем словарь в DataFrame
        # Разделяем на категории для лучшей читаемости
        categories = {
            'Абсолютные показатели ($)': [
                'total_invested', 'portfolio_value', 'total_div_received', 'net_result'
            ],
            'Относительные показатели (%)': [
                'roi_pct', 'cagr_pct', 'final_yield_on_cost',
                'best_year_return_pct', 'worst_year_return_pct', 'max_drawdown_pct'
            ],
            'Портфельные показатели': [
                'total_shares', 'avg_cost_basis', 'final_price'
            ]
        }

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            for category_name, metric_keys in categories.items():
                # Фильтруем существующие метрики
                category_data = {}
                for key in metric_keys:
                    if key in summary:
                        category_data[key] = summary[key]

                if category_data:
                    df_category = pd.DataFrame(
                        list(category_data.items()),
                        columns=['Метрика', 'Значение']
                    )
                    df_category.to_excel(
                        writer,
                        sheet_name=category_name[:31],  # Ограничение длины имени листа
                        index=False
                    )

        logger.debug(f"Создан Excel файл сводных метрик: {file_path}")
        return file_path


# Синглтон-экземпляр для удобства
_exporter_instance: Optional[TableExporter] = None


def get_table_exporter(output_dir: Path = TABLES_DIR) -> TableExporter:
    """
    Возвращает глобальный экземпляр экспортёра таблиц (синглтон).

    Parameters
    ----------
    output_dir : Path
        Директория для сохранения файлов.

    Returns
    -------
    TableExporter
        Экземпляр экспортёра.
    """
    global _exporter_instance
    if _exporter_instance is None:
        _exporter_instance = TableExporter(output_dir)
    return _exporter_instance


if __name__ == "__main__":
    # Простой тест экспортёра
    print("Тестовый запуск TableExporter...")
    print("-" * 50)

    try:
        exporter = TableExporter()

        # Создаём тестовые данные
        test_df = pd.DataFrame({
            'year': [2000, 2001, 2002],
            'price': [100.0, 110.0, 90.0],
            'total_invested': [1000, 2000, 3000],
            'portfolio_value': [950, 2200, 2800]
        })

        test_summary = {
            'total_invested': 3000,
            'portfolio_value': 2800,
            'net_result': -200,
            'roi_pct': -6.67
        }

        test_validation = {
            'is_valid': True,
            'messages': ['Все проверки пройдены'],
            'report_text': 'Отчёт валидации: OK'
        }

        # Тест экспорта
        print("1. Экспорт таблицы симуляции...")
        files1 = exporter.export_simulation_table(
            test_df, 'TEST', 2000, 2002, 1000, True, formats=['csv', 'xlsx']
        )
        print(f"   Создано файлов: {len(files1)}")

        print("\n2. Экспорт сводных метрик...")
        files2 = exporter.export_summary_table(
            test_summary, 'TEST', 2000, 2002, 1000, True, formats=['json', 'xlsx']
        )
        print(f"   Создано файлов: {len(files2)}")

        print("\n3. Экспорт отчёта валидации...")
        file3 = exporter.export_validation_report(
            test_validation, 'TEST', 2000, 2002, 1000, True
        )
        print(f"   Создан файл: {file3}")

        print("\n✅ Все тесты прошли успешно!")

    except Exception as e:
        print(f"❌ Ошибка при тесте экспортёра: {e}")
        import traceback

        traceback.print_exc()