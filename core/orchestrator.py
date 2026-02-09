"""
Главный координатор (оркестратор) для выполнения сценариев анализа.
Управляет последовательностью этапов: загрузка данных → валидация → расчёт → отчёт.
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import pandas as pd
from pandas import DataFrame
import logging

from core.config import (
    TICKER, START_YEAR, END_YEAR, ANNUAL_INVESTMENT, REINVEST_DIVIDENDS,
    TABLES_DIR, GRAPHS_DIR, generate_report_filename, setup_project_dirs
)
from core.data_provider import get_data_provider
from core.data_validator import get_validator
from core.portfolio_simulator import PortfolioSimulator
from core.table_exporter import get_table_exporter

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AnalysisOrchestrator:
    """
    Оркестратор для выполнения полного цикла анализа стратегии DCA.
    Реализует паттерн "шаги" (steps) для гибкого расширения.
    """

    def __init__(
            self,
            ticker: str = TICKER,
            start_year: int = START_YEAR,
            end_year: int = END_YEAR,
            annual_investment: float = ANNUAL_INVESTMENT,
            reinvest_dividends: bool = REINVEST_DIVIDENDS,
            strict_validation: bool = True
    ):
        """
        Инициализация оркестратора с параметрами анализа.

        Parameters
        ----------
        ticker : str
            Тикер анализируемой бумаги.
        start_year : int
            Год начала инвестирования.
        end_year : int
            Год окончания инвестирования.
        annual_investment : float
            Ежегодная сумма инвестиций (USD).
        reinvest_dividends : bool
            Флаг реинвестирования дивидендов.
        strict_validation : bool
            Режим строгой валидации данных.
        """
        self.ticker = ticker.upper()
        self.start_year = start_year
        self.end_year = end_year
        self.annual_investment = annual_investment
        self.reinvest_dividends = reinvest_dividends
        self.strict_validation = strict_validation

        # Состояние выполнения (будет заполняться на каждом этапе)
        self.execution_state: Dict[str, Any] = {
            'start_time': None,
            'end_time': None,
            'current_step': None,
            'errors': [],
            'warnings': []
        }

        # Результаты этапов
        self.results: Dict[str, Any] = {
            'raw_data': None,  # DataFrame с загруженными данными
            'filtered_data': None,  # DataFrame отфильтрованный по периоду
            'validation_report': None,  # Отчёт валидации
            'portfolio_simulation': None,  # Результаты симуляции (будет позже)
            'final_report': None  # Итоговый отчёт (будет позже)
        }

        # Регистрация этапов (будет расширяться)
        self._steps = [
            ('setup_directories', self._step_setup_directories),
            ('load_data', self._step_load_data),
            ('validate_data', self._step_validate_data),
            ('simulate_portfolio', self._step_simulate_portfolio),
            ('export_tables', self._step_export_tables),
            # Здесь будут добавлены этапы:
            # ('generate_reports', self._step_generate_reports)
        ]

        logger.info(f"Инициализирован оркестратор для {ticker} "
                    f"({start_year}-{end_year}, ${annual_investment}/год)")

    def run(self) -> Dict[str, Any]:
        """
        Запускает полный цикл анализа.

        Returns
        -------
        Dict[str, Any]
            Словарь с результатами выполнения всех этапов.
        """
        self.execution_state['start_time'] = time.time()
        logger.info("=" * 60)
        logger.info(f"Запуск анализа для {self.ticker}")
        logger.info("=" * 60)

        try:
            for step_name, step_func in self._steps:
                self.execution_state['current_step'] = step_name
                logger.info(f"Выполнение этапа: {step_name}")

                step_success = step_func()

                if not step_success:
                    error_msg = f"Этап {step_name} завершился с ошибкой"
                    logger.error(error_msg)
                    self.execution_state['errors'].append(error_msg)
                    break

            self.execution_state['end_time'] = time.time()
            execution_time = self.execution_state['end_time'] - self.execution_state['start_time']

            logger.info(f"Анализ завершён за {execution_time:.2f} сек")
            self._print_summary()

        except Exception as e:
            logger.error(f"Критическая ошибка при выполнении: {e}", exc_info=True)
            self.execution_state['errors'].append(str(e))

        return {
            'execution_state': self.execution_state,
            'results': self.results
        }

    # ========== ЭТАПЫ ВЫПОЛНЕНИЯ ==========

    def _step_setup_directories(self) -> bool:
        """Этап 1: Создание структуры директорий проекта."""
        try:
            setup_project_dirs()
            logger.info("✓ Структура директорий создана/проверена")
            return True
        except Exception as e:
            logger.error(f"Ошибка создания директорий: {e}")
            return False

    def _step_load_data(self) -> bool:
        """Этап 2: Загрузка и фильтрация исторических данных."""
        try:
            provider = get_data_provider()

            # Загружаем все данные по тикеру
            raw_data = provider.load_ticker_data(self.ticker)
            self.results['raw_data'] = raw_data
            logger.info(f"✓ Загружены данные: {len(raw_data)} записей "
                        f"({raw_data['year'].min()}-{raw_data['year'].max()})")

            # Фильтруем по запрошенному периоду
            filtered_data = provider.load_data_for_period(
                ticker=self.ticker,
                start_year=self.start_year,
                end_year=self.end_year
            )
            self.results['filtered_data'] = filtered_data
            logger.info(f"✓ Отфильтровано по периоду: {len(filtered_data)} записей "
                        f"({self.start_year}-{self.end_year})")

            return True

        except FileNotFoundError as e:
            logger.error(f"Файл с данными не найден: {e}")
            return False
        except ValueError as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка загрузки: {e}")
            return False

    def _step_validate_data(self) -> bool:
        """Этап 3: Валидация загруженных данных."""
        try:
            data_to_validate = self.results['filtered_data']
            if data_to_validate is None:
                logger.error("Нет данных для валидации")
                return False

            validator = get_validator(strict_mode=self.strict_validation)
            is_valid, messages = validator.validate_dataframe(data_to_validate, self.ticker)

            self.results['validation_report'] = {
                'is_valid': is_valid,
                'messages': messages,
                'report_text': validator.get_validation_report(self.ticker)
            }

            if is_valid:
                logger.info("✓ Данные прошли валидацию")
                if messages:
                    logger.info(f"  Предупреждения: {len(messages)}")
            else:
                logger.warning("✗ Данные не прошли валидацию")
                for msg in messages:
                    logger.warning(f"  - {msg}")

            # В strict_mode=False продолжаем даже с ошибками валидации
            return True if not self.strict_validation else is_valid

        except Exception as e:
            logger.error(f"Ошибка валидации: {e}")
            return False

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _print_summary(self) -> None:
        """Выводит краткую сводку выполнения."""
        logger.info("\n" + "=" * 60)
        logger.info("СВОДКА ВЫПОЛНЕНИЯ")
        logger.info("=" * 60)

        if self.execution_state['errors']:
            logger.error(f"Ошибок: {len(self.execution_state['errors'])}")
            for err in self.execution_state['errors']:
                logger.error(f"  • {err}")
        else:
            logger.info("✓ Все этапы выполнены успешно")

        # Информация о загруженных данных
        if self.results['filtered_data'] is not None:
            df = self.results['filtered_data']
            logger.info(f"Данные: {self.ticker}, {len(df)} записей "
                        f"({self.start_year}-{self.end_year})")

        # Время выполнения
        if self.execution_state['end_time']:
            total_time = self.execution_state['end_time'] - self.execution_state['start_time']
            logger.info(f"Время выполнения: {total_time:.2f} сек")

    def add_step(self, step_name: str, step_function: Callable[[], bool]) -> None:
        """
        Добавляет пользовательский этап в конвейер выполнения.

        Parameters
        ----------
        step_name : str
            Название этапа (для логирования).
        step_function : Callable[[], bool]
            Функция этапа, возвращающая bool (успех/неудача).
        """
        self._steps.append((step_name, step_function))
        logger.info(f"Добавлен пользовательский этап: {step_name}")

    def get_available_data(self) -> Optional[DataFrame]:
        """
        Возвращает отфильтрованные данные, если они загружены.

        Returns
        -------
        Optional[DataFrame]
            DataFrame с данными за указанный период или None.
        """
        return self.results['filtered_data']

    def get_validation_result(self) -> Optional[Dict[str, Any]]:
        """
        Возвращает результаты валидации.

        Returns
        -------
        Optional[Dict[str, Any]]
            Словарь с результатами валидации или None.
        """
        return self.results['validation_report']

    def _step_simulate_portfolio(self) -> bool:
        """Этап 4: Симуляция портфеля по стратегии DCA."""
        try:
            filtered_data = self.results['filtered_data']
            if filtered_data is None:
                logger.error("Нет данных для симуляции")
                return False

            # Проверяем, что данные прошли валидацию (в strict mode)
            if self.strict_validation:
                validation_result = self.results['validation_report']
                if validation_result and not validation_result['is_valid']:
                    logger.error("Данные не прошли валидацию. Симуляция прервана.")
                    return False

            simulator = PortfolioSimulator(
                annual_investment=self.annual_investment,
                reinvest_dividends=self.reinvest_dividends
            )

            simulation_results = simulator.simulate(
                filtered_data,
                start_year=self.start_year,
                end_year=self.end_year
            )

            self.results['portfolio_simulation'] = simulation_results
            self.results['simulation_df'] = simulation_results['simulation_df']
            self.results['simulation_summary'] = simulation_results['summary']
            self.results['simulation_params'] = simulation_results['parameters']

            logger.info(f"✓ Симуляция портфеля завершена")
            logger.info(f"  Период: {self.start_year}-{self.end_year}")
            logger.info(f"  Чистая прибыль: ${simulation_results['summary']['net_result']:.2f}")
            logger.info(f"  ROI: {simulation_results['summary']['roi_pct']:.1f}%")

            return True

        except NotImplementedError as e:
            logger.error(f"Ошибка конфигурации симулятора: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка симуляции портфеля: {e}")
            return False

    def get_simulation_results(self) -> Optional[Dict[str, Any]]:
        """
        Возвращает результаты симуляции портфеля.

        Returns
        -------
        Optional[Dict[str, Any]]
            Словарь с результатами симуляции или None.
        """
        return self.results.get('portfolio_simulation')

    def _step_export_tables(self) -> bool:
        """Этап 5: Экспорт результатов в табличные форматы (CSV, Excel, JSON)."""
        try:
            # Проверяем наличие необходимых данных
            if self.results.get('simulation_df') is None:
                logger.error("Нет данных симуляции для экспорта")
                return False

            simulation_df = self.results['simulation_df']
            source_df = self.results.get('filtered_data')
            summary_metrics = self.results.get('simulation_summary', {})
            validation_result = self.results.get('validation_report', {})

            # Получаем экспортёр
            exporter = get_table_exporter()

            # 1. Экспортируем таблицу симуляции
            sim_files = exporter.export_simulation_table(
                simulation_df=simulation_df,
                source_df=source_df,
                ticker=self.ticker,
                start_year=self.start_year,
                end_year=self.end_year,
                annual_investment=self.annual_investment,
                reinvest_div=self.reinvest_dividends,
                formats=['xlsx', 'csv'],
                export_final_report=True
            )

            # 2. Экспортируем сводные метрики
            if summary_metrics:
                summary_files = exporter.export_summary_table(
                    summary_metrics=summary_metrics,
                    ticker=self.ticker,
                    start_year=self.start_year,
                    end_year=self.end_year,
                    annual_investment=self.annual_investment,
                    reinvest_div=self.reinvest_dividends,
                    formats=['json', 'xlsx']
                )
            else:
                summary_files = {}
                logger.warning("Нет сводных метрик для экспорта")

            # 3. Экспортируем отчёт валидации
            if validation_result:
                validation_file = exporter.export_validation_report(
                    validation_result=validation_result,
                    ticker=self.ticker,
                    start_year=self.start_year,
                    end_year=self.end_year,
                    annual_investment=self.annual_investment,
                    reinvest_div=self.reinvest_dividends
                )
            else:
                validation_file = None
                logger.warning("Нет отчёта валидации для экспорта")

            # Сохраняем информацию о созданных файлах
            self.results['exported_files'] = {
                'simulation': sim_files,
                'summary': summary_files,
                'validation': validation_file
            }

            # Логируем результаты
            total_files = len(sim_files) + len(summary_files) + (1 if validation_file else 0)
            logger.info(f"✓ Экспорт таблиц завершён. Создано файлов: {total_files}")

            # Выводим пути к основным файлам
            if 'xlsx' in sim_files:
                logger.info(f"  Основной файл: {sim_files['xlsx'].name}")
            if 'json' in summary_files:
                logger.info(f"  Сводные метрики: {summary_files['json'].name}")

            return True

        except Exception as e:
            logger.error(f"Ошибка экспорта таблиц: {e}")
            return False


# Фабричная функция для удобства
def create_orchestrator(
        ticker: str = TICKER,
        start_year: int = START_YEAR,
        end_year: int = END_YEAR,
        annual_investment: float = ANNUAL_INVESTMENT,
        reinvest_dividends: bool = REINVEST_DIVIDENDS,
        strict_validation: bool = True
) -> AnalysisOrchestrator:
    """
    Создаёт и возвращает экземпляр оркестратора с указанными параметрами.

    Returns
    -------
    AnalysisOrchestrator
        Настроенный экземпляр оркестратора.
    """
    return AnalysisOrchestrator(
        ticker=ticker,
        start_year=start_year,
        end_year=end_year,
        annual_investment=annual_investment,
        reinvest_dividends=reinvest_dividends,
        strict_validation=strict_validation
    )


if __name__ == "__main__":
    # Тестовый запуск оркестратора (только загрузка и валидация)
    print("Тестовый запуск оркестратора...")
    print("-" * 50)

    orchestrator = create_orchestrator(
        ticker=TICKER,
        start_year=START_YEAR,
        end_year=END_YEAR,
        annual_investment=ANNUAL_INVESTMENT,
        reinvest_dividends=REINVEST_DIVIDENDS,
        strict_validation=False
    )

    results = orchestrator.run()

    # Проверка результатов
    if results['execution_state']['errors']:
        print("\n❌ Были ошибки при выполнении:")
        for err in results['execution_state']['errors']:
            print(f"  - {err}")
    else:
        print("\n✅ Все этапы выполнены успешно")

        # Показываем загруженные данные
        data = orchestrator.get_available_data()
        if data is not None:
            print(f"\nЗагружено записей: {len(data)}")
            print(f"Период: {data['year'].min()} - {data['year'].max()}")
            print("\nПервые 3 записи:")
            print(data[['date', 'year', 'price', 'div_annual']].head(3).to_string())

        # Показываем отчёт валидации
        validation = orchestrator.get_validation_result()
        if validation:
            print(f"\nРезультат валидации: {'ПРОЙДЕНА' if validation['is_valid'] else 'НЕ ПРОЙДЕНА'}")
            if validation['messages']:
                print("Сообщения валидации:")
                for msg in validation['messages'][:3]:  # Показываем первые 3
                    print(f"  - {msg}")