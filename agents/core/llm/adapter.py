"""
LLM Adapter — единый интерфейс для работы с разными LLM провайдерами.
Включает retry логику (tenacity), подсчёт токенов и опциональный кэш.
"""
import hashlib
import logging
import threading
from typing import Callable, Dict, Optional, Type

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from agents.core.base_agent import ApiConfig, LLMConfig, LLMProvider, CacheProtocol
from agents.core.llm.engines.base_engine import BaseLLMEngine, LLMResponse
from agents.core.llm.engines.openai_engine import OpenAIEngine
from agents.core.llm.engines.claude_engine import ClaudeEngine
from agents.core.llm.engines.gemini_engine import GeminiEngine
from agents.core.llm.engines.mock_engine import MockEngine
from agents.core.llm.exceptions import LLMTransientError

logger = logging.getLogger(__name__)

# ── Plugin registry (модульный уровень) ───────────────────────────
#
# Единственное место глобального состояния — явный opt-in для plugin pattern.
# Регистрация нового провайдера глобально:
#     LLMAdapter.register_engine_global(LLMProvider.CUSTOM, MyEngine)
#
# Новые экземпляры LLMAdapter копируют этот dict в свой instance-level registry.
# Уже созданные экземпляры НЕ получают новый engine — только новые.
#
_PLUGIN_REGISTRY: Dict[LLMProvider, Type[BaseLLMEngine]] = {}
_PLUGIN_REGISTRY_LOCK = threading.Lock()


def _build_default_engine_registry() -> Dict[LLMProvider, Type[BaseLLMEngine]]:
    """
    Строит дефолтный реестр движков.

    Вынесен в функцию чтобы:
    - каждый вызов возвращает новый dict (изоляция между экземплярами)
    - легко переопределять в тестах
    """
    return {
        LLMProvider.OPENAI: OpenAIEngine,
        LLMProvider.CLAUDE: ClaudeEngine,
        LLMProvider.GEMINI: GeminiEngine,
        LLMProvider.MOCK: MockEngine,
    }


class LLMAdapter:
    """
    Единый интерфейс для работы с разными LLM провайдерами.

    Ответственности:
        - выбор engine по провайдеру (через dict-based registry)
        - retry с exponential backoff (только LLMTransientError)
        - кэширование ответов (опционально)
        - подсчёт использованных токенов

    Engine registry (два уровня):
        1. Plugin-level: LLMAdapter.register_engine_global() — модульный dict.
           Регистрирует провайдер для всех будущих экземпляров.
           Используется для plugin-расширений.
        2. Instance-level: передаётся через конструктор engine_registry=...
           или собирается из дефолтов + plugin registry при создании.
           Каждый экземпляр полностью изолирован — тесты не влияют друг на друга.
    """

    def __init__(
        self,
        config: LLMConfig,
        api_config: Optional[ApiConfig] = None,
        cache: Optional[CacheProtocol] = None,
        engine_registry: Optional[Dict[LLMProvider, Type[BaseLLMEngine]]] = None,
    ):
        """
        Args:
            config: конфигурация LLM (провайдер, модель, температура)
            api_config: конфигурация API (ключ, base_url, retries)
            cache: опциональный кэш (реализует CacheProtocol)
            engine_registry: опциональный реестр движков для этого экземпляра.
                Если None — собирается из дефолтов + plugin registry.
                Передайте явно в тестах для полной изоляции:
                    adapter = LLMAdapter(config, engine_registry={LLMProvider.MOCK: MyMock})
        """
        self.config = config
        self.api_config = api_config or ApiConfig()
        self.cache = cache

        # Instance-level registry: полностью изолирован от других экземпляров.
        #
        # Приоритет сборки:
        #   1. Явно переданный engine_registry (тесты, кастомные сборки)
        #   2. Дефолты + зарегистрированные плагины (обычное использование)
        #
        # Копируем dict чтобы мутации этого экземпляра не влияли на другие.
        if engine_registry is not None:
            self._engine_registry: Dict[LLMProvider, Type[BaseLLMEngine]] = dict(engine_registry)
        else:
            # Дефолты + плагины: плагины перекрывают дефолты если совпадает ключ
            registry = _build_default_engine_registry()
            with _PLUGIN_REGISTRY_LOCK:
                registry.update(_PLUGIN_REGISTRY)
            self._engine_registry = registry

        self.engine: BaseLLMEngine = self._init_engine()
        self._tokens_used: int = 0
        self._lock = threading.Lock()

        self._call_with_retry = self._make_retry(self._call_engine, is_async=False)
        self._acall_with_retry = self._make_retry(self._acall_engine, is_async=True)

        logger.debug(
            "LLMAdapter инициализирован: provider=%s, model=%s, retries=%d",
            config.provider,
            config.model,
            self.api_config.retries,
        )

    # ── Plugin registry (модульный уровень) ───────────────────────

    @classmethod
    def register_engine_global(
        cls,
        provider: LLMProvider,
        engine_class: Type[BaseLLMEngine],
    ) -> None:
        """
        Регистрирует новый engine глобально — для всех будущих экземпляров.

        Plugin pattern: позволяет добавлять провайдеры без изменения кода адаптера.
        Уже созданные экземпляры НЕ получают новый engine — только новые.

        Глобальное состояние хранится в модульном _PLUGIN_REGISTRY,
        не в class variable — изолировано от instance state.

        Args:
            provider: идентификатор провайдера
            engine_class: класс engine (наследник BaseLLMEngine)

        Пример:
            LLMAdapter.register_engine_global(LLMProvider.CUSTOM, MyCustomEngine)
            adapter = LLMAdapter(LLMConfig(provider="custom"))  # видит MyCustomEngine
        """
        if not issubclass(engine_class, BaseLLMEngine):
            raise TypeError(
                f"{engine_class.__name__} должен быть наследником BaseLLMEngine"
            )
        with _PLUGIN_REGISTRY_LOCK:
            _PLUGIN_REGISTRY[provider] = engine_class
        logger.info(
            "LLMAdapter: глобально зарегистрирован engine %s для провайдера '%s'",
            engine_class.__name__, provider,
        )

    # Обратная совместимость: старое имя register_engine → новое register_engine_global
    @classmethod
    def register_engine(
        cls,
        provider: LLMProvider,
        engine_class: Type[BaseLLMEngine],
    ) -> None:
        """
        Устаревший алиас для register_engine_global().
        Оставлен для обратной совместимости.
        """
        cls.register_engine_global(provider, engine_class)

    def register_engine_local(
        self,
        provider: LLMProvider,
        engine_class: Type[BaseLLMEngine],
    ) -> None:
        """
        Регистрирует engine только для этого экземпляра.

        Полезно в тестах для подмены конкретного провайдера
        без влияния на другие экземпляры.

        Args:
            provider: идентификатор провайдера
            engine_class: класс engine (наследник BaseLLMEngine)
        """
        if not issubclass(engine_class, BaseLLMEngine):
            raise TypeError(
                f"{engine_class.__name__} должен быть наследником BaseLLMEngine"
            )
        self._engine_registry[provider] = engine_class
        logger.debug(
            "LLMAdapter: локально зарегистрирован engine %s для провайдера '%s'",
            engine_class.__name__, provider,
        )

    @classmethod
    def list_providers(cls) -> list:
        """Список провайдеров: дефолты + зарегистрированные плагины."""
        registry = _build_default_engine_registry()
        with _PLUGIN_REGISTRY_LOCK:
            registry.update(_PLUGIN_REGISTRY)
        return list(registry.keys())

    # ── engine init ───────────────────────────────────────────────

    def _init_engine(self) -> BaseLLMEngine:
        """
        Создаёт engine по провайдеру из instance-level registry.
        """
        engine_class = self._engine_registry.get(self.config.provider)

        if engine_class is None:
            available = list(self._engine_registry.keys())
            raise ValueError(
                f"Неизвестный провайдер: {self.config.provider}. "
                f"Доступные: {available}. "
                f"Добавьте провайдер через LLMAdapter.register_engine_global()."
            )

        if self.config.provider == LLMProvider.MOCK:
            return engine_class(self.config)

        return engine_class(self.config, self.api_config)

    # ── retry factory (unified) ───────────────────────────────────

    def _make_retry(self, fn: Callable, *, is_async: bool) -> Callable:
        """
        Единая фабрика retry-обёрток для sync и async функций.
        """
        decorator = retry(
            stop=stop_after_attempt(self.api_config.retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(LLMTransientError),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        wrapped = decorator(fn)
        logger.debug(
            "LLMAdapter: retry настроен для %s (%s, attempts=%d)",
            fn.__name__,
            "async" if is_async else "sync",
            self.api_config.retries,
        )
        return wrapped

    # ── engine calls (без retry, без кэша) ────────────────────────

    def _call_engine(self, prompt: str) -> str:
        """Один синхронный вызов engine."""
        try:
            llm_response: LLMResponse = self.engine.call(prompt)
        except LLMTransientError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Неожиданная ошибка LLM: {exc}") from exc

        self._add_tokens(llm_response.tokens_used)
        return llm_response.text

    async def _acall_engine(self, prompt: str) -> str:
        """Один асинхронный вызов engine."""
        try:
            llm_response: LLMResponse = await self.engine.acall(prompt)
        except LLMTransientError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Неожиданная ошибка LLM: {exc}") from exc

        self._add_tokens(llm_response.tokens_used)
        return llm_response.text

    # ── cache helpers ─────────────────────────────────────────────

    def _cache_key(self, prompt: str) -> str:
        """Генерирует ключ кэша из промпта + параметров модели."""
        components = (
            prompt,
            str(self.config.provider),
            self.config.model,
            f"{self.config.temperature:.4f}",
            str(self.config.max_tokens),
        )
        combined = "|".join(components)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _cache_get(self, prompt: str) -> Optional[str]:
        """Проверяет кэш."""
        if self.cache is None:
            return None
        key = self._cache_key(prompt)
        cached = self.cache.get(key)
        if cached is not None:
            logger.debug("Cache hit для промпта (key=%s...)", key[:12])
        return cached

    def _cache_set(self, prompt: str, response: str) -> None:
        """Сохраняет ответ в кэш."""
        if self.cache is None:
            return
        key = self._cache_key(prompt)
        self.cache.set(key, response)

    # ── token tracking ────────────────────────────────────────────

    def _add_tokens(self, count: int) -> None:
        """Потокобезопасно добавляет токены к счётчику."""
        with self._lock:
            self._tokens_used += count

    def get_tokens_used(self) -> int:
        """Возвращает суммарное количество использованных токенов."""
        with self._lock:
            return self._tokens_used

    def reset_tokens(self) -> None:
        """Сбрасывает счётчик токенов."""
        with self._lock:
            self._tokens_used = 0

    # ── public: sync ──────────────────────────────────────────────

    def call(self, prompt: str) -> str:
        """
        Синхронный вызов LLM.
        Порядок: cache check → engine call (с retry) → cache save.
        """
        cached = self._cache_get(prompt)
        if cached is not None:
            return cached

        response = self._call_with_retry(prompt)
        self._cache_set(prompt, response)
        return response

    # ── public: async ─────────────────────────────────────────────

    async def acall(self, prompt: str) -> str:
        """
        Асинхронный вызов LLM.
        Порядок: cache check → async engine call (с retry) → cache save.
        """
        cached = self._cache_get(prompt)
        if cached is not None:
            return cached

        response = await self._acall_with_retry(prompt)
        self._cache_set(prompt, response)
        return response