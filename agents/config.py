"""
Конфигурация проекта.
Загружает настройки из переменных окружения и/или YAML-файлов.
"""
import os
import logging
from pathlib import Path
from typing import Optional

from agents.core.base_agent import (
    AgentConfig,
    AgentMode,
    ApiConfig,
    LLMConfig,
    LLMProvider,
)


logger = logging.getLogger(__name__)


def load_llm_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMConfig:
    """
    Загружает LLMConfig из переменных окружения.

    Env vars:
        LLM_PROVIDER: openai | claude | gemini | mock
        LLM_MODEL: название модели (gpt-4, claude-3-opus и т.д.)
        LLM_TEMPERATURE: float [0, 2]
        LLM_MAX_TOKENS: int > 0
        LLM_TIMEOUT: int (секунды)
    """
    return LLMConfig(
        provider=LLMProvider(provider or os.getenv("LLM_PROVIDER", "mock")),
        model=model or os.getenv("LLM_MODEL", "gpt-4"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1000")),
        timeout_seconds=int(os.getenv("LLM_TIMEOUT", "30")),
    )


def load_api_config() -> ApiConfig:
    """
    Загружает ApiConfig из переменных окружения.

    Env vars:
        API_BASE_URL: базовый URL
        API_KEY: ключ API (или OPENAI_API_KEY / ANTHROPIC_API_KEY)
        API_RETRIES: количество повторов
        API_TIMEOUT: таймаут в секундах
    """
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        # Пробуем провайдер-специфичные ключи
        api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = os.getenv("GOOGLE_API_KEY", "")

    if not api_key:
        logger.warning("API ключ не найден в переменных окружения")

    return ApiConfig(
        base_url=os.getenv("API_BASE_URL", ""),
        api_key=api_key,
        retries=int(os.getenv("API_RETRIES", "3")),
        timeout_seconds=int(os.getenv("API_TIMEOUT", "30")),
    )


def load_agent_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    cache_enabled: bool = True,
) -> AgentConfig:
    """
    Собирает полную конфигурацию агента из env.

    Args:
        provider: переопределение провайдера (приоритет над env)
        model: переопределение модели (приоритет над env)
        cache_enabled: включить кэш

    Returns:
        AgentConfig
    """
    config = AgentConfig(
        mode=AgentMode.API,
        llm_config=load_llm_config(provider=provider, model=model),
        api_config=load_api_config(),
        cache_enabled=cache_enabled,
    )
    logger.info(
        "Загружена конфигурация: provider=%s, model=%s, cache=%s",
        config.llm_config.provider.value,
        config.llm_config.model,
        config.cache_enabled,
    )
    return config


def try_load_yaml_config(path: str = "config.yaml") -> Optional[dict]:
    """
    Пытается загрузить YAML-конфигурацию.
    Возвращает None если файл не найден или yaml не установлен.
    """
    config_path = Path(path)
    if not config_path.exists():
        logger.debug("YAML конфиг не найден: %s", path)
        return None

    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        logger.info("Загружен YAML конфиг из %s", path)
        return data
    except ImportError:
        logger.debug("PyYAML не установлен, YAML конфиг пропущен")
        return None
    except Exception as e:
        logger.error("Ошибка чтения YAML конфига: %s", e)
        return None