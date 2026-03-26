"""
In-memory кэш для LLM ответов.
Реализует CacheProtocol из base_agent.py.
"""
import logging
import threading
from collections import OrderedDict
from typing import Optional


logger = logging.getLogger(__name__)


class InMemoryCache:
    """
    Простой in-memory LRU кэш.

    Реализует CacheProtocol для использования в LLMAdapter.
    Потокобезопасный.
    """

    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        """Получить значение из кэша. None если не найдено."""
        with self._lock:
            if key in self._cache:
                # LRU: перемещаем в конец
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def set(self, key: str, value: str) -> None:
        """Сохранить значение в кэш. Вытесняет старые при переполнении."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug("Кэш: вытеснён ключ %s", evicted_key[:16])

    def clear(self) -> None:
        """Очистить весь кэш."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Текущий размер кэша."""
        with self._lock:
            return len(self._cache)