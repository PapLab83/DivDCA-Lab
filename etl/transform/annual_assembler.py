"""
Модуль для сборки годового датасета.
Соединяет цены (31 декабря), агрегированные дивиденды, сплиты и reasons.
"""
from datetime import date
from collections import defaultdict
from typing import List, Dict

from .models import (
    RawPrice, AggregatedDividend, RawSplit, RawReason,
    YearlyData, TransformedRecord
)


def _get_year_range(prices: List[RawPrice]) -> range:
    """Определяет диапазон лет из списка цен."""
    if not prices:
        return range(0)
    years = [p.year for p in prices]
    return range(min(years), max(years) + 1)


def _get_price_on_dec31(prices: List[RawPrice], year: int) -> tuple[date | None, float | None]:
    """
    Находит цену на 31 декабря для указанного года.
    Возвращает (дата, цена) или (None, None) если нет данных.
    """
    dec31 = date(year, 12, 31)

    # Ищем точное совпадение
    for p in prices:
        if p.date == dec31:
            return p.date, p.price

    # Если нет 31 декабря, берем последнюю цену в году
    year_prices = [p for p in prices if p.year == year]
    if year_prices:
        last = max(year_prices, key=lambda x: x.date)
        return last.date, last.price

    return None, None


def _get_splits_by_year(splits: List[RawSplit]) -> Dict[int, List[RawSplit]]:
    """Группирует сплиты по годам."""
    result = defaultdict(list)
    for split in splits:
        result[split.year].append(split)
    return dict(result)


def _get_reasons_by_year(reasons: List[RawReason]) -> Dict[int, RawReason]:
    """Индексирует reasons по году (предполагаем один reason на год)."""
    return {r.year: r for r in reasons}


def _build_split_description(splits: List[RawSplit]) -> str | None:
    """
    Формирует текстовое описание сплитов для года.
    Пример: "Сплит 2:1 в июне, сплит 1.5:1 в ноябре"
    """
    if not splits:
        return None

    descriptions = []
    for s in splits:
        month = s.date.strftime("%B").lower()
        if s.split_type:
            descriptions.append(f"{s.split_type} в {month}")
        else:
            ratio = s.split_ratio
            if ratio > 1:
                descriptions.append(f"сплит {int(ratio)}:1 в {month}")
            else:
                descriptions.append(f"обратный сплит 1:{int(1 / ratio)} в {month}")

    return ", ".join(descriptions)


def _merge_reason_with_split(
        reason: RawReason | None,
        split_desc: str | None
) -> tuple[str | None, str | None]:
    """
    Объединяет информацию из reason с информацией о сплитах.
    Возвращает (reason_short, reason_long)
    """
    if not reason and not split_desc:
        return None, None

    if not reason:
        return "Сплит", f"В этом году произошел сплит: {split_desc}"

    if not split_desc:
        return reason.reason_short, reason.reason_long

    # Есть и reason, и сплит — добавляем информацию о сплите в long
    short = reason.reason_short
    long = f"{reason.reason_long}\n\nСплит: {split_desc}"
    return short, long


def assemble(
        prices: List[RawPrice],
        dividends: List[AggregatedDividend],
        splits: List[RawSplit],
        reasons: List[RawReason]
) -> List[TransformedRecord]:
    """
    Собирает финальный датасет по годам.

    Args:
        prices: список цен (уже скорректированных)
        dividends: список агрегированных дивидендов по годам
        splits: список сплитов
        reasons: список причин по годам

    Returns:
        список TransformedRecord для всех лет, где есть цена
    """
    if not prices:
        return []

    # Подготавливаем данные
    years_range = _get_year_range(prices)
    dividends_by_year = {d.year: d for d in dividends}
    splits_by_year = _get_splits_by_year(splits)
    reasons_by_year = _get_reasons_by_year(reasons)

    result = []

    for year in years_range:
        # 1. Цена на 31 декабря
        price_date, price_value = _get_price_on_dec31(prices, year)
        if price_value is None:
            continue  # пропускаем годы без цен

        # 2. Дивиденды за год
        div = dividends_by_year.get(year)
        div_annual = div.total_dividend if div else 0.0

        # 3. Сплиты за год
        year_splits = splits_by_year.get(year, [])
        split_desc = _build_split_description(year_splits)

        # 4. Причина
        reason = reasons_by_year.get(year)

        # 5. Объединяем reason со сплитами
        reason_short, reason_long = _merge_reason_with_split(reason, split_desc)

        # 6. Создаем финальную запись
        record = TransformedRecord(
            date=price_date,
            year=year,
            price=round(price_value, 4),
            div_annual=round(div_annual, 4),
            reason_short=reason_short,
            reason_long=reason_long
        )
        result.append(record)

    return result