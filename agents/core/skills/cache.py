"""
In-memory кэш для LLM ответов.
Реализует CacheProtocol из base_agent.py.
"""

__all__ = [
    "InMemoryCache",
]

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    """
    Внутренняя запись кэша.

    Attributes:
        value: кэшированное значение
        expires_at: монотонное время истечения (None → бессрочно)
    """
    value: str
    expires_at: Optional[float]  # time.monotonic() + ttl_seconds, или None

    def is_expired(self) -> bool:
        """Проверяет истечение TTL."""
        if self.expires_at is None:
            return False
        return time.monotonic() >= self.expires_at


class InMemoryCache:
    """
    Простой in-memory LRU кэш с опциональным TTL.

    Реализует CacheProtocol для использования в LLMAdapter.
    Потокобезопасный.

    Args:
        max_size: максимальное количество записей (LRU eviction при переполнении)
        ttl_seconds: время жизни записи в секундах.
            None (default) → записи хранятся бессрочно (поведение как раньше).
            Передайте значение для автоматической инвалидации устаревших LLM-ответов.

    Пример:
        # Без TTL (поведение по умолчанию, обратная совместимость):
        cache = InMemoryCache(max_size=1000)

        # С TTL 1 час:
        cache = InMemoryCache(max_size=1000, ttl_seconds=3600.0)

        # С TTL 24 часа для долгоживущих процессов:
        cache = InMemoryCache(max_size=500, ttl_seconds=86400.0)
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: Optional[float] = None):
        # ИЗМЕНЕНО: добавлен параметр ttl_seconds.
        # None → бессрочное хранение (обратная совместимость со старым поведением).
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError(
                f"ttl_seconds должен быть положительным, получено: {ttl_seconds}"
            )
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        """
        Получить значение из кэша. None если не найдено или истёк TTL.

        ИЗМЕНЕНО: при обращении к истёкшей записи — удаляем её (lazy eviction)
        и возвращаем None, как если бы записи не было.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # ИЗМЕНЕНО: проверка TTL при каждом get()
            if entry.is_expired():
                del self._cache[key]
                logger.debug("Кэш: истёк TTL для ключа %s...", key[:12])
                return None

            # LRU: перемещаем в конец
            self._cache.move_to_end(key)
            return entry.value

    def set(self, key: str, value: str) -> None:
        """
        Сохранить значение в кэш. Вытесняет старые при переполнении.
        """
        with self._lock:
            expires_at = (
                time.monotonic() + self._ttl_seconds
                if self._ttl_seconds is not None
                else None
            )
            entry = _CacheEntry(value=value, expires_at=expires_at)

            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = entry

            if len(self._cache) > self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug("Кэш: вытеснён ключ %s...", evicted_key[:16])

    def clear(self) -> None:
        """Очистить весь кэш."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """
        Текущий размер кэша (включая потенциально истёкшие записи).

        Истёкшие записи удаляются лениво при get() — size() не выполняет
        полный обход для точного подсчёта живых записей (производительность).
        """
        with self._lock:
            return len(self._cache)

    def evict_expired(self) -> int:
        """
        Принудительно удаляет все истёкшие записи.

        Полезно вызывать периодически если кэш долго не читается,
        но нужно освободить память. В обычном режиме инвалидация
        происходит лениво при get().

        Returns:
            Количество удалённых записей.
        """
        with self._lock:
            expired_keys = [
                k for k, entry in self._cache.items()
                if entry.is_expired()
            ]
            for k in expired_keys:
                del self._cache[k]
            if expired_keys:
                logger.debug("Кэш: принудительно удалено %d истёкших записей", len(expired_keys))
            return len(expired_keys)

    def __repr__(self) -> str:
        return (
            f"InMemoryCache("
            f"max_size={self._max_size}, "
            f"ttl_seconds={self._ttl_seconds!r}, "
            f"size={self.size()})"
        )