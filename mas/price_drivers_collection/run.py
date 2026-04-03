"""
Точка входа: python -m mas.price_drivers_collection.run

Env vars:
    LLM_PROVIDER:  mock | openai | claude | gemini (default: mock)
    OPENAI_API_KEY: ключ API (если provider != mock)
    DATA_SOURCE:   mock | ... (default: mock, в будущем: db, csv, api)
"""
import json
import logging
import os
import sys
from typing import Any, Dict, List

from agents.config import build_container
from agents.tasks.event_generation.agent import EventGenerationAgent
from mas.price_drivers_collection.orchestrator import run_collection


logger = logging.getLogger(__name__)


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


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("agents.core.llm").setLevel(logging.WARNING)
    logging.getLogger("agents.core.agent_factory").setLevel(logging.WARNING)
    logging.getLogger("agents.core.agent_registry").setLevel(logging.WARNING)


def main() -> None:
    setup_logging()

    data_source = os.getenv("DATA_SOURCE", "mock")
    logger.info("DATA_SOURCE=%s", data_source)

    # 1. Собираем контейнер
    container = build_container()
    logger.info(
        "Контейнер: provider=%s, model=%s",
        container.config.llm_config.provider,
        container.config.llm_config.model,
    )

    # 2. Регистрируем агента
    container.factory.register("event_generation", EventGenerationAgent)
    logger.info("Агенты: %s", container.factory.list_agents())

    # 3. Загружаем данные
    tickers_data = load_data(data_source)

    # 4. Запускаем оркестрацию
    results = run_collection(container, tickers_data)

    # 5. Выводим результаты
    logger.info("=" * 60)
    logger.info("РЕЗУЛЬТАТЫ")
    logger.info("=" * 60)

    for ticker, records in results.items():
        logger.info("--- %s ---", ticker)
        for r in records:
            if r["success"]:
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
    logger.info("FULL JSON:\n%s", json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()