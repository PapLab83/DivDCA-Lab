"""
Конфигурация проекта.
Загружает настройки из переменных окружения и/или YAML-файлов.

Приоритет: ENV vars → YAML config → defaults в коде.
"""
import os
import logging
from pathlib import Path
from typing import Dict, Optional, Type

from agents.core.base_agent import (
    AgentConfig,
    AgentMode,
    ApiConfig,
    LLMConfig,
    LLMProvider,
)
from agents.core.container import Container
from agents.core.llm.engines.base_engine import BaseLLMEngine


logger = logging.getLogger(__name__)


def load_llm_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    yaml_overrides: Optional[dict] = None,
) -> LLMConfig:
    """
    Загружает LLMConfig.

    Приоритет: аргументы функции → ENV vars → YAML overrides → defaults.

    Args:
        provider: явный провайдер (приоритет над ENV и YAML)
        model: явная модель (приоритет над ENV и YAML)
        yaml_overrides: секция llm из YAML-конфига (fallback перед defaults)

    Env vars:
        LLM_PROVIDER: openai | claude | gemini | mock
        LLM_MODEL: название модели (gpt-4, claude-3-opus и т.д.)
        LLM_TEMPERATURE: float [0, 2]
        LLM_MAX_TOKENS: int > 0
        LLM_TIMEOUT: int (секунды)
    """
    yaml_llm = yaml_overrides.get("llm", {}) if yaml_overrides else {}

    def _env_or_yaml(env_key: str, yaml_key: str, default):
        """
        Возвращает значение по приоритету: ENV → YAML → default.
        Использует явную проверку на None чтобы корректно обрабатывать
        falsy-значения (0, 0.0, "") из переменных окружения.
        """
        env_val = os.getenv(env_key)
        if env_val is not None:
            return env_val
        yaml_val = yaml_llm.get(yaml_key)
        if yaml_val is not None:
            return yaml_val
        return default

    return LLMConfig(
        provider=LLMProvider(
            provider
            or os.getenv("LLM_PROVIDER")
            or yaml_llm.get("provider", "mock")
        ),
        model=(
            model
            or os.getenv("LLM_MODEL")
            or yaml_llm.get("model", "gpt-4")
        ),
        temperature=float(_env_or_yaml("LLM_TEMPERATURE", "temperature", 0.7)),
        max_tokens=int(_env_or_yaml("LLM_MAX_TOKENS", "max_tokens", 1000)),
        timeout_seconds=int(_env_or_yaml("LLM_TIMEOUT", "timeout_seconds", 30)),
    )


def load_api_config(yaml_overrides: Optional[dict] = None) -> ApiConfig:
    """
    Загружает ApiConfig.

    Приоритет: ENV vars → YAML overrides → defaults.

    Args:
        yaml_overrides: секция api из YAML-конфига (fallback перед defaults)

    Env vars:
        API_BASE_URL: базовый URL
        API_KEY: ключ API (или OPENAI_API_KEY / ANTHROPIC_API_KEY)
        API_RETRIES: количество повторов
        API_TIMEOUT: таймаут в секундах
    """
    yaml_api = yaml_overrides.get("api", {}) if yaml_overrides else {}

    _API_KEY_ENV_PRIORITY = [
        "API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
    ]

    api_key = next(
        (os.getenv(var) for var in _API_KEY_ENV_PRIORITY if os.getenv(var)),
        yaml_api.get("api_key", ""),
    )

    if not api_key:
        logger.warning("API ключ не найден в переменных окружения и YAML-конфиге")

    return ApiConfig(
        base_url=os.getenv("API_BASE_URL") or yaml_api.get("base_url", ""),
        api_key=api_key,
        retries=int(os.getenv("API_RETRIES") or yaml_api.get("retries", 3)),
        timeout_seconds=int(os.getenv("API_TIMEOUT") or yaml_api.get("timeout_seconds", 30)),
    )


def load_agent_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    cache_enabled: bool = True,
    prompts_path: Optional[str] = None,
    yaml_overrides: Optional[dict] = None,
) -> AgentConfig:
    """
    Собирает полную конфигурацию агента.

    Args:
        provider: явный провайдер
        model: явная модель
        cache_enabled: включить кэш
        prompts_path: путь к директории с YAML-промптами.
            Приоритет: аргумент → ENV (PROMPTS_PATH) → None (Container использует дефолт).
        yaml_overrides: данные из YAML-конфига (fallback перед defaults)

    Env vars:
        PROMPTS_PATH: путь к директории с промптами
    """
    resolved_prompts_path = (
        prompts_path
        or os.getenv("PROMPTS_PATH")
        or (yaml_overrides.get("prompts_path") if yaml_overrides else None)
    )

    config = AgentConfig(
        mode=AgentMode.API,
        llm_config=load_llm_config(
            provider=provider,
            model=model,
            yaml_overrides=yaml_overrides,
        ),
        api_config=load_api_config(yaml_overrides=yaml_overrides),
        cache_enabled=cache_enabled,
        prompts_path=resolved_prompts_path,
    )
    logger.info(
        "Загружена конфигурация: provider=%s, model=%s, cache=%s, prompts_path=%s",
        config.llm_config.provider,
        config.llm_config.model,
        config.cache_enabled,
        config.prompts_path or "<default>",
    )
    return config


def try_load_yaml_config(path: str = "config.yaml") -> Optional[dict]:
    """
    Пытается загрузить YAML-конфигурацию.

    Возвращает dict с настройками или None если файл не найден
    или yaml не установлен.

    Ожидаемая структура YAML:
        llm:
          provider: openai
          model: gpt-4
          temperature: 0.7
          max_tokens: 1000
          timeout_seconds: 30
        api:
          base_url: ""
          api_key: ""
          retries: 3
          timeout_seconds: 30
        prompts_path: "agents/prompts"
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


def build_container(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    cache_enabled: bool = True,
    prompts_path: Optional[str] = None,
    config_path: str = "config.yaml",
    engine_registry: Optional[Dict[LLMProvider, Type[BaseLLMEngine]]] = None,
) -> Container:
    """
    Собирает полный DI-контейнер.

    Приоритет конфигурации: аргументы → ENV vars → YAML файл → defaults.

    Args:
        provider: явный провайдер (приоритет над всем)
        model: явная модель (приоритет над всем)
        cache_enabled: включить кэш
        prompts_path: путь к директории с промптами (приоритет над ENV и YAML).
            None → читается из ENV PROMPTS_PATH → YAML prompts_path → дефолт пакета.
        config_path: путь к YAML-конфигу (default: config.yaml)
        engine_registry: реестр LLM-движков для контейнера.
            Рекомендуемый способ добавления кастомных провайдеров.
            None → используются дефолтные провайдеры (OpenAI, Claude, Gemini, Mock).

            Пример добавления провайдера:
                from agents.core.llm.engines.base_engine import BaseLLMEngine

                class MyCustomEngine(BaseLLMEngine):
                    ...

                container = build_container(
                    provider="custom",
                    engine_registry={LLMProvider.CUSTOM: MyCustomEngine},
                )

    Использование:
        container = build_container(provider="openai")
        container = build_container(prompts_path="configs/prompts/")
        container = build_container(config_path="configs/prod.yaml")
        agent = container.factory.create_agent(...)
    """
    yaml_overrides = try_load_yaml_config(config_path)
    if yaml_overrides:
        logger.info(
            "YAML конфиг применён как fallback: %s (секции: %s)",
            config_path,
            list(yaml_overrides.keys()),
        )

    config = load_agent_config(
        provider=provider,
        model=model,
        cache_enabled=cache_enabled,
        prompts_path=prompts_path,
        yaml_overrides=yaml_overrides,
    )
    return Container(config, engine_registry=engine_registry)