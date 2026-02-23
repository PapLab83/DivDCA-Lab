"""
Модуль для агрегации дивидендов по годам.
Суммирует все выплаты за календарный год.
"""
from collections import defaultdict
from typing import List

from ..models import RawDividend, AggregatedDividend


def aggregate(dividends: List[RawDividend]) -> List[AggregatedDividend]:
    """
    Агрегирует дивиденды по годам.

    Args:
        dividends: список сырых дивидендов (уже скорректированных на сплиты)

    Returns:
        список AggregatedDividend по годам, отсортированный по году

    Пример:
        Вход: [
            RawDividend(date=2023-02-01, dividend=0.5),
            RawDividend(date=2023-05-01, dividend=0.5),
            RawDividend(date=2024-02-01, dividend=0.6)
        ]
        Выход: [
            AggregatedDividend(year=2023, total_dividend=1.0, payment_count=2),
            AggregatedDividend(year=2024, total_dividend=0.6, payment_count=1)
        ]
    """
    if not dividends:
        return []

    # Группируем по году
    yearly = defaultdict(lambda: {"total": 0.0, "count": 0})

    for div in dividends:
        yearly[div.year]["total"] += div.dividend
        yearly[div.year]["count"] += 1

    # Преобразуем в список моделей
    result = [
        AggregatedDividend(
            year=year,
            total_dividend=data["total"],
            payment_count=data["count"]
        )
        for year, data in sorted(yearly.items())
    ]

    return result


def aggregate_with_gaps(dividends: List[RawDividend], years_range: range) -> List[AggregatedDividend]:
    """
    Агрегирует дивиденды и гарантирует наличие всех лет в диапазоне.
    Для лет без выплат ставит total_dividend=0, payment_count=0.

    Args:
        dividends: список сырых дивидендов
        years_range: диапазон лет, которые должны присутствовать

    Returns:
        список AggregatedDividend для всех лет в диапазоне
    """
    aggregated = aggregate(dividends)
    agg_by_year = {a.year: a for a in aggregated}

    result = []
    for year in years_range:
        if year in agg_by_year:
            result.append(agg_by_year[year])
        else:
            result.append(AggregatedDividend(
                year=year,
                total_dividend=0.0,
                payment_count=0
            ))

    return result