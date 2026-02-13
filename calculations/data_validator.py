"""
Модуль для расширенной валидации исторических данных.
Проверяет логическую целостность, отсутствие аномалий и соответствие бизнес-правилам.
"""
from typing import List, Tuple, Optional
import pandas as pd
from pandas import DataFrame

from config.config import START_YEAR, END_YEAR, TICKER


class DataValidator:
    """
    Валидатор исторических данных по акциям.
    Выполняет проверки целостности, консистентности и логики данных.
    """

    def __init__(self, strict_mode: bool = True):
        """
        Инициализация валидатора.

        Parameters
        ----------
        strict_mode : bool, default True
            Если True, выбрасывает исключения при обнаружении проблем.
            Если False, только собирает предупреждения.
        """
        self.strict_mode = strict_mode
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def validate_dataframe(self, df: DataFrame, ticker: str = TICKER) -> Tuple[bool, List[str]]:
        """
        Основной метод валидации DataFrame с историческими данными.

        Parameters
        ----------
        df : DataFrame
            DataFrame с данными, загруженный через LocalJsonDataProvider.
        ticker : str
            Тикер для информационных сообщений.

        Returns
        -------
        Tuple[bool, List[str]]
            (is_valid, list_of_messages)
            is_valid = True если данные прошли все критичные проверки.
        """
        self.warnings.clear()
        self.errors.clear()

        # 1. Базовая проверка структуры
        self._validate_structure(df, ticker)

        # 2. Проверка временных рядов
        self._validate_time_series(df, ticker)

        # 3. Проверка числовых значений на аномалии
        self._validate_numeric_ranges(df, ticker)

        # 4. Проверка логики дивидендов
        self._validate_dividend_logic(df, ticker)

        # 5. Проверка соответствия запрошенному периоду
        self._validate_period_coverage(df, ticker)

        # Формируем итоговый отчёт
        all_messages = self.errors + self.warnings
        is_valid = len(self.errors) == 0

        if self.strict_mode and not is_valid:
            error_summary = "\n".join(self.errors)
            raise ValueError(
                f"Валидация данных для {ticker} провалена:\n{error_summary}"
            )

        return is_valid, all_messages

    def _validate_structure(self, df: DataFrame, ticker: str) -> None:
        """Проверяет наличие и тип обязательных колонок."""
        required_columns = {
            'date': 'datetime64[ns]',
            'year': 'int64',
            'price': 'float64',
            'div_annual': 'float64'
        }

        for col, dtype in required_columns.items():
            if col not in df.columns:
                self.errors.append(f"Отсутствует обязательная колонка: '{col}'")
            elif not pd.api.types.is_dtype_equal(df[col].dtype, dtype):
                self.warnings.append(
                    f"Колонка '{col}' имеет тип {df[col].dtype}, ожидается {dtype}"
                )

        # Проверяем наличие опциональных колонок
        optional_columns = ['reason_short', 'reason_long']
        for col in optional_columns:
            if col not in df.columns:
                self.warnings.append(f"Отсутствует опциональная колонка: '{col}'")

    def _validate_time_series(self, df: DataFrame, ticker: str) -> None:
        """Проверяет целостность временного ряда."""
        # Проверка на уникальность дат
        duplicate_dates = df['date'][df['date'].duplicated()]
        if not duplicate_dates.empty:
            self.errors.append(
                f"Обнаружены дублирующиеся даты: {duplicate_dates.tolist()}"
            )

        # Проверка на пропуски в последовательности дат
        date_series = df['date'].sort_values()
        expected_frequency = pd.DateOffset(years=1)
        date_diffs = date_series.diff().dropna()

        # Допускаем разницу в +/- 5 дней от годового интервала
        max_diff = pd.Timedelta(days=370)
        min_diff = pd.Timedelta(days=360)

        anomalous_diffs = date_diffs[(date_diffs > max_diff) | (date_diffs < min_diff)]
        if not anomalous_diffs.empty:
            self.errors.append(
                f"Обнаружены аномальные интервалы между датами: {anomalous_diffs.tolist()}"
            )

        # Проверка сортировки
        if not df['date'].is_monotonic_increasing:
            self.warnings.append("Даты не отсортированы в хронологическом порядке")

    def _validate_numeric_ranges(self, df: DataFrame, ticker: str) -> None:
        """Проверяет числовые значения на допустимые диапазоны."""
        # Проверка цен
        price_series = df['price']
        if (price_series <= 0).any():
            self.errors.append("Обнаружены неположительные значения цены")

        # Проверка на выбросы цен (цена > 10 * медианной)
        price_median = price_series.median()
        price_outliers = price_series[price_series > price_median * 10]
        if not price_outliers.empty:
            self.warnings.append(
                f"Обнаружены возможные выбросы в ценах: {price_outliers.tolist()}"
            )

        # Проверка дивидендов
        div_series = df['div_annual']
        if (div_series < 0).any():
            self.errors.append("Обнаружены отрицательные дивиденды")

        # Дивиденды не должны превышать 50% от цены (подозрительно высокая доходность)
        suspicious_div = df[div_series > price_series * 0.5]
        if not suspicious_div.empty:
            self.warnings.append(
                f"Подозрительно высокие дивиденды (>50% от цены) в годах: "
                f"{suspicious_div['year'].tolist()}"
            )

        # Проверка на пропуски
        numeric_cols = ['price', 'div_annual']
        for col in numeric_cols:
            if df[col].isna().any():
                self.errors.append(f"Обнаружены пропуски в колонке '{col}'")

    def _validate_dividend_logic(self, df: DataFrame, ticker: str) -> None:
        """
        Проверяет логику дивидендных выплат.
        Для дивидендных аристократов проверяет неубывающий тренд.
        """
        # Проверка на непрерывный рост дивидендов (для аристократов)
        div_series = df['div_annual'].sort_index()

        # Считаем количество лет с уменьшением дивидендов
        div_decreases = (div_series.diff() < 0).sum()

        if div_decreases > 0:
            self.warnings.append(
                f"Дивиденды уменьшались {div_decreases} раз за период. "
                f"Для дивидендных аристократов это нехарактерно."
            )

        # Проверка на нулевые дивиденды
        zero_div_years = df[df['div_annual'] == 0]['year'].tolist()
        if zero_div_years:
            self.warnings.append(
                f"Нулевые дивиденды в годах: {zero_div_years}. "
                f"Убедитесь, что это корректно для {ticker}."
            )

    def _validate_period_coverage(self, df: DataFrame, ticker: str) -> None:
        """Проверяет, что данные покрывают запрошенный период."""
        min_year = df['year'].min()
        max_year = df['year'].max()

        if START_YEAR < min_year:
            self.errors.append(
                f"Запрошенный начальный год {START_YEAR} раньше, "
                f"чем доступные данные (с {min_year})"
            )

        if END_YEAR > max_year:
            self.errors.append(
                f"Запрошенный конечный год {END_YEAR} позже, "
                f"чем доступные данные (по {max_year})"
            )

        # Проверяем, что все годы в запрошенном диапазоне присутствуют
        expected_years = set(range(START_YEAR, END_YEAR + 1))
        actual_years = set(df['year'])
        missing_years = expected_years - actual_years

        if missing_years:
            self.errors.append(
                f"Отсутствуют данные за годы: {sorted(missing_years)}"
            )

    def get_validation_report(self, ticker: str = TICKER) -> str:
        """
        Формирует текстовый отчёт о результатах валидации.

        Returns
        -------
        str
            Отформатированный отчёт.
        """
        report_lines = []
        report_lines.append(f"Отчёт валидации данных для {ticker}")
        report_lines.append("=" * 50)

        if self.errors:
            report_lines.append("\n❌ КРИТИЧЕСКИЕ ОШИБКИ:")
            for i, error in enumerate(self.errors, 1):
                report_lines.append(f"  {i}. {error}")

        if self.warnings:
            report_lines.append("\n⚠️  ПРЕДУПРЕЖДЕНИЯ:")
            for i, warning in enumerate(self.warnings, 1):
                report_lines.append(f"  {i}. {warning}")

        if not self.errors and not self.warnings:
            report_lines.append("\n✅ Все проверки пройдены успешно.")

        status = "ВАЛИДНЫ" if not self.errors else "НЕВАЛИДНЫ"
        report_lines.append(f"\nСтатус: Данные {status}")
        report_lines.append(f"Режим strict_mode: {'ВКЛ' if self.strict_mode else 'ВЫКЛ'}")

        return "\n".join(report_lines)


# Синглтон-экземпляр для удобства
_validator_instance: Optional[DataValidator] = None

def get_validator(strict_mode: bool = True) -> DataValidator:
    """
    Возвращает глобальный экземпляр валидатора (синглтон).

    Parameters
    ----------
    strict_mode : bool, default True
        Режим строгой валидации.

    Returns
    -------
    DataValidator
        Экземпляр валидатора.
    """
    global _validator_instance
    if _validator_instance is None or _validator_instance.strict_mode != strict_mode:
        _validator_instance = DataValidator(strict_mode=strict_mode)
    return _validator_instance


if __name__ == "__main__":
    # Тест валидатора с загрузкой данных
    from calculations.data_provider import get_data_provider

    try:
        provider = get_data_provider()
        data = provider.load_ticker_data("JNJ")

        validator = DataValidator(strict_mode=False)
        is_valid, messages = validator.validate_dataframe(data, "JNJ")

        print(validator.get_validation_report("JNJ"))
        print(f"\nis_valid: {is_valid}")

        if not is_valid:
            print("\nСообщения:")
            for msg in messages:
                print(f"  - {msg}")

    except Exception as e:
        print(f"❌ Ошибка при тесте валидатора: {e}")
        import traceback
        traceback.print_exc()