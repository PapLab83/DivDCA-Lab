# mas/price_drivers_collection/data_loader.py
"""
Registry загрузчиков данных.

Паттерн: Registry + Callable.
Добавление нового источника — регистрация функции, без изменения load_data().

Использование:
    # Регистрация нового источника:
    register_loader("csv", lambda: load_from_csv("data.csv"))

    # Загрузка:
    data = load_data("mock")
    data = load_data("csv")

    # Список доступных:
    list_sources()  # ["mock", "csv", ...]
"""
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# Тип загрузчика: callable без аргументов → список тикеров
DataLoader = Callable[[], List[Dict[str, Any]]]

# Registry загрузчиков. Ключ — имя источника, значение — callable.
# Добавляй новые источники через register_loader() или напрямую в этот dict.
_LOADER_REGISTRY: Dict[str, DataLoader] = {}


def register_loader(source: str, loader: DataLoader) -> None:
    """
    Регистрирует загрузчик данных для источника.

    Args:
        source: строковый идентификатор источника ("mock", "db", "csv", "api")
        loader: callable () → List[TickerData]

    Использование:
        register_loader("csv", lambda: load_from_csv("data/tickers.csv"))
        register_loader("db", lambda: DBLoader(conn_string).load())
    """
    _LOADER_REGISTRY[source] = loader
    logger.debug("DataLoader: зарегистрирован источник '%s'", source)


def list_sources() -> List[str]:
    """Список зарегистрированных источников данных."""
    return list(_LOADER_REGISTRY.keys())


def load_data(source: str) -> List[Dict[str, Any]]:
    """
    Загружает данные из зарегистрированного источника.

    Args:
        source: идентификатор источника

    Returns:
        Список тикеров с записями

    Raises:
        ValueError: источник не зарегистрирован
    """
    loader = _LOADER_REGISTRY.get(source)
    if loader is None:
        available = list_sources()
        raise ValueError(
            f"Неизвестный DATA_SOURCE: '{source}'. "
            f"Доступные: {available}. "
            f"Зарегистрируйте новый через register_loader()."
        )

    logger.info("DataLoader: загрузка из источника '%s'", source)
    data = loader()
    logger.info("DataLoader: загружено %d тикеров из '%s'", len(data), source)
    return data


# ── Регистрация встроенных источников ────────────────────────────

def _load_mock() -> List[Dict[str, Any]]:
    """Загружает mock-данные."""
    from mas.price_drivers_collection.mock_data import MOCK_TICKERS
    return list(MOCK_TICKERS)


# Встроенные источники регистрируются при импорте модуля.
# Новые источники регистрируются в app_factory.py или точке входа.
register_loader("mock", _load_mock)