# mas/price_drivers_collection/run.py
"""
Точка входа: python -m mas.price_drivers_collection.run

Env vars:
    LLM_PROVIDER:  mock | openai | claude | gemini (default: mock)
    OPENAI_API_KEY: ключ API (если provider != mock)
    DATA_SOURCE:   mock | ... (default: mock, в будущем: db, csv, api)
    USER_PROFILE:  conservative | moderate | aggressive (default: conservative)
"""
import json
import logging
import os
import sys
from typing import Any, Dict, List, Callable

from agents.core.profiles import AggressivenessLevel, UserProfile
from mas.price_drivers_collection.app_factory import (
    build_app_container,
    build_event_generation_agent,
)
from mas.price_drivers_collection.orchestrator import run_collection

logger = logging.getLogger(__name__)


# ── Загрузка данных ───────────────────────────────────────────────

def load_data(source: str) -> List[Dict[str, Any]]:
    """
    Загружает данные из указанного источника.

    Args:
        source: идентификатор источника данных

    Returns:
        Список тикеров с записями

    Raises:
        ValueError: неизвестный источник
    """
    if source == "mock":
        from mas.price_drivers_collection.mock_data import MOCK_TICKERS
        logger.info("Загружены мок-данные: %d тикеров", len(MOCK_TICKERS))
        return MOCK_TICKERS

    raise ValueError(
        f"Неизвестный DATA_SOURCE: '{source}'. "
        f"Доступные: mock"
    )


# ── Загрузка профиля ──────────────────────────────────────────────

def load_profile(level: str) -> UserProfile:
    """
    Создаёт UserProfile по имени уровня из ENV.

    Args:
        level: "conservative" | "moderate" | "aggressive"

    Returns:
        UserProfile соответствующего уровня.
        Если уровень неизвестен — возвращает conservative с предупреждением.
    """
    profile_map: Dict[str, Callable[[], UserProfile]] = {
        str(AggressivenessLevel.CONSERVATIVE): UserProfile.conservative,
        str(AggressivenessLevel.MODERATE): UserProfile.moderate,
        str(AggressivenessLevel.AGGRESSIVE): UserProfile.aggressive,
    }

    factory = profile_map.get(level)
    if factory is None:
        logger.warning(
            "Неизвестный USER_PROFILE='%s'. "
            "Доступные: %s. Используется 'conservative'.",
            level,
            list(profile_map.keys()),
        )
        return UserProfile.conservative()

    return factory()


# ── Форматирование результатов ────────────────────────────────────

def format_results(results: Dict[str, List[Dict[str, Any]]]) -> None:
    """
    Выводит результаты оркестрации в лог.

    Args:
        results: {ticker: [результаты по годам]}
    """
    logger.info("=" * 60)
    logger.info("РЕЗУЛЬТАТЫ")
    logger.info("=" * 60)

    for ticker, records in results.items():
        logger.info("--- %s ---", ticker)
        for r in records:
            if r["success"] and r.get("data"):
                data = r["data"]
                logger.info(
                    "  %d: %s (confidence=%s, %sms)",
                    r["year"],
                    data.get("reason_short", "?"),
                    data.get("confidence", "?"),
                    r["duration_ms"],
                )
            else:
                logger.info("  %d: ERROR — %s", r["year"], r["error"])

    logger.info("=" * 60)
    logger.info(
        "FULL JSON:\n%s",
        json.dumps(results, indent=2, ensure_ascii=False),
    )


# ── Настройка логирования ─────────────────────────────────────────

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("agents.core.llm").setLevel(logging.WARNING)
    logging.getLogger("agents.core.agent_factory").setLevel(logging.WARNING)
    logging.getLogger("agents.core.agent_registry").setLevel(logging.WARNING)


# ── Точка входа ───────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    data_source = os.getenv("DATA_SOURCE", "mock")
    logger.info("DATA_SOURCE=%s", data_source)

    # 1. Собираем контейнер и регистрируем агентов
    container = build_app_container()

    # 2. Создаём агента один раз — до цикла по тикерам.
    #    Агент stateless: один экземпляр безопасно переиспользуется
    #    для всех тикеров и всех лет.
    agent = build_event_generation_agent(container)

    # 3. Загружаем данные
    tickers_data = load_data(data_source)

    # 4. UserProfile — читаем из ENV, fallback → conservative
    profile_level = os.getenv("USER_PROFILE", AggressivenessLevel.CONSERVATIVE)
    profile = load_profile(profile_level)
    logger.info("UserProfile: %s", profile)

    # 5. Запускаем оркестрацию
    results = run_collection(
        agent=agent,
        tickers_data=tickers_data,
        profile=profile,
    )

    # 6. Выводим результаты
    format_results(results)


if __name__ == "__main__":
    main()