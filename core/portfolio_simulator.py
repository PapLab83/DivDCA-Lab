"""
Модуль для симуляции портфеля по стратегии DCA (усреднение стоимости).
Рассчитывает денежные потоки, стоимость портфеля и ключевые метрики.
"""
from typing import Dict, Any, Optional
import pandas as pd
from pandas import DataFrame
import numpy as np
import logging

from core.config import ANNUAL_INVESTMENT, REINVEST_DIVIDENDS

logger = logging.getLogger(__name__)


class PortfolioSimulator:
    """
    Симулятор портфеля для стратегии DCA с фиксированными ежегодными инвестициями.
    Рассчитывает пошаговую динамику портфеля с учётом дивидендов.
    """

    def __init__(
        self,
        annual_investment: float = ANNUAL_INVESTMENT,
        reinvest_dividends: bool = REINVEST_DIVIDENDS
    ):
        """
        Инициализация симулятора.

        Parameters
        ----------
        annual_investment : float
            Фиксированная сумма ежегодных инвестиций (USD).
        reinvest_dividends : bool
            Флаг реинвестирования дивидендов.
            ВНИМАНИЕ: На текущий момент реализована ТОЛЬКО стратегия с реинвестированием (True).
        """
        if not reinvest_dividends:
            raise NotImplementedError(
                "Режим без реинвестирования дивидендов (reinvest_dividends=False) "
                "временно не поддерживается."
            )

        self.annual_investment = annual_investment
        self.reinvest_dividends = reinvest_dividends

        # Кэш результатов
        self._simulation_results: Optional[DataFrame] = None
        self._summary_metrics: Optional[Dict[str, Any]] = None

    def simulate(
        self,
        historical_data: DataFrame,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Основной метод симуляции портфеля на исторических данных.

        Parameters
        ----------
        historical_data : DataFrame
            DataFrame с историческими данными (обязательные колонки:
            'date', 'year', 'price', 'div_annual').
        start_year : int, optional
            Год начала симуляции. Если не указан, берётся первый год в данных.
        end_year : int, optional
            Год окончания симуляции. Если не указан, берётся последний год в данных.

        Returns
        -------
        Dict[str, Any]
            Словарь с результатами:
            - 'simulation_df': DataFrame с пошаговыми результатами
            - 'summary': сводные метрики
            - 'parameters': параметры симуляции
        """
        logger.info(f"Запуск симуляции DCA (${self.annual_investment}/год, "
                   f"реинвест дивидендов: {self.reinvest_dividends})")

        # Подготовка данных
        df = self._prepare_data(historical_data, start_year, end_year)
        n_years = len(df)

        if n_years == 0:
            raise ValueError("Нет данных для симуляции в указанном периоде.")

        # Инициализация массивов для результатов
        years = df['year'].values
        prices = df['price'].values
        dividends = df['div_annual'].values

        # Основные массивы для расчётов (начинаем с 0)
        shares_bought = np.zeros(n_years)        # Акций куплено в этом году
        total_shares = np.zeros(n_years)         # Накопленное количество акций
        total_invested = np.zeros(n_years)       # Всего вложено денег
        portfolio_value = np.zeros(n_years)      # Стоимость портфеля
        div_received = np.zeros(n_years)         # Дивиденды полученные в этом году
        total_div_received = np.zeros(n_years)   # Накопленные дивиденды
        net_result = np.zeros(n_years)           # Чистый финансовый результат

        # Первый год (год 0 в массивах)
        shares_bought[0] = self.annual_investment / prices[0]
        total_shares[0] = shares_bought[0]
        total_invested[0] = self.annual_investment
        portfolio_value[0] = total_shares[0] * prices[0]
        # Дивиденды за первый год не получаем (покупка в конце года)
        net_result[0] = portfolio_value[0] - total_invested[0]

        # Основной цикл симуляции
        for i in range(1, n_years):
            # 1. Получаем дивиденды за прошлый год
            div_received[i] = total_shares[i-1] * dividends[i-1]
            total_div_received[i] = total_div_received[i-1] + div_received[i]

            # 2. Реинвестируем дивиденды (покупаем дополнительные акции)
            div_shares = div_received[i] / prices[i] if prices[i] > 0 else 0

            # 3. Делаем регулярную ежегодную покупку
            regular_shares = self.annual_investment / prices[i]

            # 4. Обновляем общее количество акций
            shares_bought[i] = regular_shares + div_shares
            total_shares[i] = total_shares[i-1] + shares_bought[i]

            # 5. Обновляем общие вложения (только регулярные инвестиции)
            total_invested[i] = total_invested[i-1] + self.annual_investment

            # 6. Рассчитываем текущую стоимость портфеля
            portfolio_value[i] = total_shares[i] * prices[i]

            # 7. Чистый результат (стоимость портфеля + полученные дивиденды - вложения)
            net_result[i] = (portfolio_value[i] + total_div_received[i]) - total_invested[i]

        # Создаём DataFrame с результатами
        results_df = pd.DataFrame({
            'year': years,
            'price': prices,
            'div_annual': dividends,
            'shares_bought': shares_bought,
            'total_shares': total_shares,
            'total_invested': total_invested,
            'portfolio_value': portfolio_value,
            'div_received': div_received,
            'total_div_received': total_div_received,
            'net_result': net_result
        })

        # Добавляем производные метрики
        results_df = self._calculate_derived_metrics(results_df)

        # Рассчитываем сводные метрики
        summary = self._calculate_summary_metrics(results_df)

        # Сохраняем в кэш
        self._simulation_results = results_df
        self._summary_metrics = summary

        logger.info(f"Симуляция завершена. Период: {years[0]}-{years[-1]}, "
                   f"лет: {n_years}")
        logger.info(f"Итоговые метрики: Чистая прибыль = ${net_result[-1]:.2f}, "
                   f"ROI = {summary['roi_pct']:.1f}%")

        return {
            'simulation_df': results_df,
            'summary': summary,
            'parameters': {
                'annual_investment': self.annual_investment,
                'reinvest_dividends': self.reinvest_dividends,
                'start_year': int(years[0]),
                'end_year': int(years[-1]),
                'n_years': n_years
            }
        }

    def _prepare_data(
        self,
        df: DataFrame,
        start_year: Optional[int],
        end_year: Optional[int]
    ) -> DataFrame:
        """
        Подготавливает данные для симуляции: фильтрация, сортировка, проверка.
        """
        # Проверяем обязательные колонки
        required_cols = ['year', 'date', 'price', 'div_annual']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Отсутствуют обязательные колонки: {missing_cols}")

        # Копируем и сортируем
        df = df.copy()
        if not df['date'].is_monotonic_increasing:
            df = df.sort_values('date')

        # Фильтрация по периоду
        if start_year is not None:
            df = df[df['year'] >= start_year]
        if end_year is not None:
            df = df[df['year'] <= end_year]

        if len(df) == 0:
            raise ValueError("После фильтрации по периоду данных не осталось.")

        # Проверяем непрерывность ряда (примерно годовые интервалы)
        df['date_diff'] = df['date'].diff().dt.days
        avg_diff = df['date_diff'].iloc[1:].mean()
        if not (300 < avg_diff < 400):
            logger.warning(f"Средний интервал между датами: {avg_diff:.0f} дней. "
                          f"Ожидается ~365 дней.")

        return df.reset_index(drop=True)

    def _calculate_derived_metrics(self, df: DataFrame) -> DataFrame:
        """
        Рассчитывает производные метрики на основе основных расчётов.
        """
        # 1. Усреднённая цена входа (Average Cost Basis)
        df['avg_cost'] = df['total_invested'] / df['total_shares']
        df['avg_cost'] = df['avg_cost'].replace([np.inf, -np.inf], np.nan)

        # 2. Доходность на成本 (Yield on Cost)
        df['yield_on_cost'] = (df['div_annual'] / df['avg_cost']) * 100

        # 3. Прирост капитала в процентах
        df['cap_gain_pct'] = ((df['portfolio_value'] - df['total_invested']) /
                              df['total_invested']) * 100

        # 4. Доходность от дивидендов в процентах
        df['div_return_pct'] = (df['total_div_received'] / df['total_invested']) * 100

        # 5. Общая доходность в процентах
        df['total_return_pct'] = df['cap_gain_pct'] + df['div_return_pct']

        # 6. Совокупный годовой темп роста (CAGR)
        # CAGR = (Ending Value / Beginning Value)^(1/n) - 1
        # Где Ending Value = portfolio_value + total_div_received
        # Beginning Value = total_invested на каждом шаге
        df['total_value'] = df['portfolio_value'] + df['total_div_received']
        df['cagr_pct'] = ((df['total_value'] / df['total_invested']) **
                          (1 / (df['year'] - df['year'].iloc[0] + 1)) - 1) * 100
        df.loc[df.index[0], 'cagr_pct'] = 0  # Первый год CAGR = 0

        # 7. Цена закрытия в начале года (для yoy_change)
        df['price_prev'] = df['price'].shift(1)
        df['yoy_change_pct'] = ((df['price'] - df['price_prev']) / df['price_prev']) * 100
        df.loc[df.index[0], 'yoy_change_pct'] = 0

        # Удаляем вспомогательные колонки
        df = df.drop(columns=['total_value', 'price_prev'])

        return df

    def _calculate_summary_metrics(self, df: DataFrame) -> Dict[str, Any]:
        """
        Рассчитывает итоговые сводные метрики по результатам симуляции.
        """
        last_row = df.iloc[-1]
        first_row = df.iloc[0]

        summary = {
            # Абсолютные денежные метрики
            'total_invested': last_row['total_invested'],
            'portfolio_value': last_row['portfolio_value'],
            'total_div_received': last_row['total_div_received'],
            'net_result': last_row['net_result'],

            # Относительные метрики (%)
            'roi_pct': last_row['total_return_pct'],  # ROI = общая доходность
            'cagr_pct': last_row['cagr_pct'],
            'final_yield_on_cost': last_row['yield_on_cost'],

            # Показатели эффективности
            'total_shares': last_row['total_shares'],
            'avg_cost_basis': last_row['avg_cost'],
            'final_price': last_row['price'],

            # Дополнительные метрики
            'max_drawdown_pct': self._calculate_max_drawdown(df),
            'best_year_return_pct': df['total_return_pct'].max(),
            'worst_year_return_pct': df['total_return_pct'].min(),
        }

        # Добавляем проверку баланса (санити-чек)
        balance_check = (last_row['portfolio_value'] + last_row['total_div_received'] -
                         last_row['total_invested'] - last_row['net_result'])
        if abs(balance_check) > 0.01:  # Допуск 1 цент
            logger.warning(f"Несходимость баланса: {balance_check:.6f}")

        return summary

    def _calculate_max_drawdown(self, df: DataFrame) -> float:
        """
        Рассчитывает максимальную просадку (max drawdown) по чистому результату.
        """
        net_result_series = df['net_result'].values
        peak = net_result_series[0]
        max_dd = 0.0

        for value in net_result_series:
            if value > peak:
                peak = value
            dd = (peak - value) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        return max_dd * 100  # В процентах

    def get_simulation_dataframe(self) -> Optional[DataFrame]:
        """
        Возвращает DataFrame с результатами последней симуляции.

        Returns
        -------
        Optional[DataFrame]
            DataFrame с результатами или None, если симуляция не проводилась.
        """
        return self._simulation_results.copy() if self._simulation_results is not None else None

    def get_summary_metrics(self) -> Optional[Dict[str, Any]]:
        """
        Возвращает сводные метрики последней симуляции.

        Returns
        -------
        Optional[Dict[str, Any]]
            Словарь с метриками или None.
        """
        return self._summary_metrics.copy() if self._summary_metrics is not None else None


if __name__ == "__main__":
    # Тестовый запуск симулятора
    print("Тестовый запуск PortfolioSimulator...")
    print("-" * 50)

    # Создаём тестовые данные (упрощённые)
    test_data = pd.DataFrame({
        'date': pd.date_range(start='2000-12-31', periods=5, freq='YE'),
        'year': [2000, 2001, 2002, 2003, 2004],
        'price': [100.0, 80.0, 90.0, 110.0, 120.0],
        'div_annual': [1.0, 1.1, 1.2, 1.3, 1.4]
    })

    print("Тестовые данные:")
    print(test_data[['year', 'price', 'div_annual']].to_string())
    print()

    try:
        simulator = PortfolioSimulator(annual_investment=1000, reinvest_dividends=True)
        results = simulator.simulate(test_data)

        print("Результаты симуляции:")
        print("-" * 50)

        df = results['simulation_df']
        print("DataFrame с результатами (первые 3 строки):")
        print(df[['year', 'price', 'total_shares', 'total_invested',
                  'portfolio_value', 'net_result']].head(3).to_string())
        print()

        print("Сводные метрики:")
        summary = results['summary']
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")

        print(f"\nПараметры: {results['parameters']}")

    except Exception as e:
        print(f"❌ Ошибка при тесте симулятора: {e}")
        import traceback
        traceback.print_exc()