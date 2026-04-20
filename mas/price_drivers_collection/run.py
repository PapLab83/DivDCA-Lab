# mas/price_drivers_collection/run.py
"""
Точка входа: python -m mas.price_drivers_collection.run

Env vars:
    LLM_PROVIDER:              mock | openai | claude | gemini (default: mock)
    OPENAI_API_KEY:            ключ API (если provider != mock)
    DATA_SOURCE:               mock | ... (default: mock)
    USER_PROFILE:              conservative | moderate | aggressive (default: conservative)
    PROMPTS_PATH:              путь к директории с промптами
    PIPELINE_CALL_TIMEOUT:     таймаут одного вызова агента в сек (default: 30.0)
    PIPELINE_RATE_LIMIT_DELAY: задержка между вызовами в сек (default: 0.0)
    PIPELINE_RATE_LIMIT_BACKOFF: множитель задержки при ошибке (default: 2.0)
    PIPELINE_MAX_WORKERS:      потоков (default: 1)
"""
import json
import logging
import os
import sys
from typing import Any, Dict, List
from dataclasses import dataclass

from agents.core.profiles import AggressivenessLevel, UserProfile
from mas.price_drivers_collection.app_factory import (
    build_app_container,
    build_event_generation_agent,
)
from mas.price_drivers_collection.orchestrator import run_collection
from mas.price_drivers_collection.pipeline import PipelineConfig
from mas.price_drivers_collection.data_loader import load_data

logger = logging.getLogger(__name__)


# ── Конфигурация запуска ──────────────────────────────────────────

@dataclass
class RunConfig:
    """
    Конфигурация одного запуска pipeline.
    Читается из ENV в _load_run_config().
    """
    data_source: str
    profile_level: str


def _load_run_config() -> RunConfig:
    """
    Читает конфигурацию запуска из ENV.

    Returns:
        RunConfig с параметрами из переменных окружения.
    """
    return RunConfig(
        data_source=os.getenv("DATA_SOURCE", "mock"),
        profile_level=os.getenv(
            "USER_PROFILE",
            str(AggressivenessLevel.CONSERVATIVE),
        ),
    )


# ── Загрузка профиля ──────────────────────────────────────────────

def _load_profile(level: str) -> UserProfile:
    """
    Создаёт UserProfile по имени уровня.

    Args:
        level: "conservative" | "moderate" | "aggressive"

    Returns:
        UserProfile. Если уровень неизвестен — conservative с предупреждением.
    """
    from typing import Callable
    profile_map: Dict[str, Callable[[], UserProfile]] = {
        str(AggressivenessLevel.CONSERVATIVE): UserProfile.conservative,
        str(AggressivenessLevel.MODERATE): UserProfile.moderate,
        str(AggressivenessLevel.AGGRESSIVE): UserProfile.aggressive,
    }
    factory = profile_map.get(level)
    if factory is None:
        logger.warning(
            "Неизвестный USER_PROFILE='%s'. Доступные: %s. Используется 'conservative'.",
            level,
            list(profile_map.keys()),
        )
        return UserProfile.conservative()
    return factory()


# ── Форматирование результатов ────────────────────────────────────

def _format_results(results: Dict[str, List[Dict[str, Any]]]) -> None:
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

def _setup_logging() -> None:
    """Настраивает базовое логирование в stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("agents.core.llm").setLevel(logging.WARNING)
    logging.getLogger("agents.core.agent_factory").setLevel(logging.WARNING)
    logging.getLogger("agents.core.agent_registry").setLevel(logging.WARNING)


# ── Шаги pipeline ─────────────────────────────────────────────────

def _build_di():
    """
    Шаг 1: сборка DI-контейнера и создание агента.

    Returns:
        Готовый агент из контейнера.
    """
    container = build_app_container()
    agent = build_event_generation_agent(container)
    return agent, container


def _prepare_data(run_config: RunConfig) -> List[Dict[str, Any]]:
    """
    Шаг 2: загрузка данных из источника.

    Args:
        run_config: конфигурация запуска

    Returns:
        Список тикеров с записями.
    """
    logger.info("DATA_SOURCE=%s", run_config.data_source)
    return load_data(run_config.data_source)


def _prepare_profile(run_config: RunConfig) -> UserProfile:
    """
    Шаг 3: загрузка профиля пользователя.

    Args:
        run_config: конфигурация запуска

    Returns:
        UserProfile.
    """
    profile = _load_profile(run_config.profile_level)
    logger.info("UserProfile: %s", profile)
    return profile


def _prepare_pipeline_config() -> PipelineConfig:
    """
    Шаг 4: загрузка конфигурации pipeline из ENV.

    Returns:
        PipelineConfig.
    """
    cfg = PipelineConfig.from_env()
    logger.info(
        "PipelineConfig: timeout=%.1fs, rate_limit_delay=%.1fs, "
        "backoff=%.1f, max_workers=%d",
        cfg.call_timeout_seconds,
        cfg.rate_limit_delay_seconds,
        cfg.rate_limit_backoff_on_error,
        cfg.max_workers,
    )
    return cfg


def _run_pipeline(
    agent,
    tickers_data: List[Dict[str, Any]],
    profile: UserProfile,
    pipeline_config: PipelineConfig,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Шаг 5: запуск оркестрации.

    Args:
        agent: готовый агент
        tickers_data: данные тикеров
        profile: профиль пользователя
        pipeline_config: конфигурация pipeline

    Returns:
        Результаты по всем тикерам.
    """
    return run_collection(
        agent=agent,
        tickers_data=tickers_data,
        profile=profile,
        pipeline_config=pipeline_config,
    )


# ── Точка входа ───────────────────────────────────────────────────

def main() -> None:
    """
    Точка входа. Последовательно выполняет шаги pipeline:
        1. Загрузка .env
        2. Настройка логирования
        3. Чтение конфигурации из ENV
        4. Сборка DI-контейнера и агента
        5. Загрузка данных
        6. Загрузка профиля
        7. Загрузка конфигурации pipeline
        8. Запуск оркестрации
        9. Вывод результатов
    """
    # 1. .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # 2. Логирование
    _setup_logging()

    # 3. Конфигурация запуска
    run_config = _load_run_config()

    # 4. DI
    agent, container = _build_di()

    # 5. Данные
    tickers_data = _prepare_data(run_config)

    # 6. Профиль
    profile = _prepare_profile(run_config)

    # 7. Pipeline config
    pipeline_config = _prepare_pipeline_config()

    # 8. Оркестрация
    results = _run_pipeline(agent, tickers_data, profile, pipeline_config)

    # 9. Вывод
    _format_results(results)


if __name__ == "__main__":
    main()