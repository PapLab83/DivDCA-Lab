"""
Anonymizer / DeAnonymizer — обезличивание данных перед передачей в LLM.

Ключевая концепция проекта (из ARCHITECTURE.md):
    LLM не должен знать реальные тикеры — это предотвращает data leakage,
    когда модель «вспоминает» из обучающих данных что AAPL вырастет в 2021.

Поток данных:
    Реальные данные → Anonymizer → LLM → DeAnonymizer → Результат

TODO (v0.3):
    - Реализовать AnonymizationMap (двусторонняя карта real ↔ anonymous)
    - Реализовать Anonymizer.anonymize_ticker()
    - Реализовать Anonymizer.anonymize_record()
    - Реализовать Anonymizer.anonymize_all()
    - Реализовать DeAnonymizer.deanonymize_ticker()
    - Реализовать DeAnonymizer.deanonymize_results()
    - Добавить стратегии: default (STOCK_0001), hash, sector-aware
"""
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────── AnonymizationMap ─────────────────────

@dataclass
class AnonymizationMap:
    """
    Двусторонняя карта соответствия реальных и анонимных идентификаторов.

    TODO (v0.3): реализовать хранение и lookup.
    """
    _real_to_anon: Dict[str, str] = field(default_factory=dict)
    _anon_to_real: Dict[str, str] = field(default_factory=dict)
    _counter: int = field(default=0)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def add(self, real: str, anonymous: str) -> None:
        """TODO (v0.3): добавить пару real ↔ anonymous."""
        raise NotImplementedError("AnonymizationMap.add не реализован. Планируется в v0.3.")

    def get_anon(self, real: str) -> Optional[str]:
        """TODO (v0.3): вернуть анонимный ID для реального."""
        raise NotImplementedError("AnonymizationMap.get_anon не реализован. Планируется в v0.3.")

    def get_real(self, anonymous: str) -> Optional[str]:
        """TODO (v0.3): вернуть реальный ID для анонимного."""
        raise NotImplementedError("AnonymizationMap.get_real не реализован. Планируется в v0.3.")

    def next_counter(self) -> int:
        """TODO (v0.3): потокобезопасный инкремент счётчика."""
        raise NotImplementedError("AnonymizationMap.next_counter не реализован. Планируется в v0.3.")

    def __len__(self) -> int:
        return len(self._real_to_anon)

    def __contains__(self, real: str) -> bool:
        return real in self._real_to_anon

    def items(self) -> List[Tuple[str, str]]:
        """TODO (v0.3): список пар (real, anonymous)."""
        raise NotImplementedError("AnonymizationMap.items не реализован. Планируется в v0.3.")

    def __repr__(self) -> str:
        return f"AnonymizationMap(size={len(self._real_to_anon)})"


# ─────────────────────────── Стратегии ────────────────────────────

class AnonymizationStrategy:
    """
    Базовая стратегия генерации анонимных идентификаторов.

    TODO (v0.3): реализовать generate().
    """

    def generate(self, real: str, counter: int) -> str:
        """
        TODO (v0.3): генерировать анонимный ID формата STOCK_0001.

        Args:
            real: реальный идентификатор
            counter: уникальный счётчик в рамках сессии
        """
        raise NotImplementedError(
            "AnonymizationStrategy.generate не реализован. Планируется в v0.3."
        )


class HashAnonymizationStrategy(AnonymizationStrategy):
    """
    Детерминированная стратегия на основе хэша.

    TODO (v0.3): реализовать generate() через SHA-256.

    ⚠️ Только для R&D — при знании алгоритма можно восстановить тикер.
    """

    def __init__(self, prefix: str = "STOCK", length: int = 6) -> None:
        self._prefix = prefix
        self._length = length

    def generate(self, real: str, counter: int) -> str:
        """TODO (v0.3): вернуть STOCK_{sha256[:length]}."""
        raise NotImplementedError(
            "HashAnonymizationStrategy.generate не реализован. Планируется в v0.3."
        )


class SectorAnonymizationStrategy(AnonymizationStrategy):
    """
    Стратегия с сохранением сектора.

    Анонимизирует тикер, но сохраняет принадлежность к сектору.
    Пример: AAPL (Tech) → TECH_0001

    TODO (v0.3): реализовать generate() с sector_map.
    """

    def __init__(self, sector_map: Optional[Dict[str, str]] = None) -> None:
        """
        Args:
            sector_map: {ticker: sector}, например {"AAPL": "TECH", "JNJ": "HEALTH"}
        """
        self._sector_map = sector_map or {}

    def generate(self, real: str, counter: int) -> str:
        """TODO (v0.3): вернуть {SECTOR}_0001 из sector_map."""
        raise NotImplementedError(
            "SectorAnonymizationStrategy.generate не реализован. Планируется в v0.3."
        )


# ─────────────────────────── Anonymizer ───────────────────────────

class Anonymizer:
    """
    Анонимизирует реальные идентификаторы (тикеры) перед передачей в LLM.

    Один экземпляр = одна сессия анонимизации.
    Карта сохраняется между вызовами — один тикер всегда получает
    один и тот же анонимный ID в рамках сессии.

    TODO (v0.3):
        - Реализовать anonymize_ticker()
        - Реализовать anonymize_record()
        - Реализовать anonymize_all()
        - Подключить AnonymizationMap и стратегии
    """

    def __init__(
        self,
        strategy: Optional[AnonymizationStrategy] = None,
        map_: Optional[AnonymizationMap] = None,
    ) -> None:
        self._strategy = strategy or AnonymizationStrategy()
        self._map = map_ or AnonymizationMap()

    @property
    def map(self) -> AnonymizationMap:
        """Карта анонимизации (для передачи в DeAnonymizer)."""
        return self._map

    def anonymize_ticker(self, real_ticker: str) -> str:
        """
        TODO (v0.3): вернуть анонимный ID для тикера.

        Сейчас возвращает реальный тикер без изменений (pass-through).
        Это безопасная заглушка: pipeline работает корректно,
        анонимизация просто не применяется.

        Args:
            real_ticker: реальный тикер (например "AAPL")

        Returns:
            Сейчас: real_ticker без изменений.
            После реализации: анонимный ID (например "STOCK_0001").
        """
        logger.debug(
            "Anonymizer.anonymize_ticker: заглушка, тикер не анонимизирован: %r",
            real_ticker,
        )
        return real_ticker

    def anonymize_record(
        self,
        real_ticker: str,
        record: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        TODO (v0.3): заменить поле 'ticker' на анонимный ID.

        Сейчас возвращает запись без изменений (pass-through).

        Args:
            real_ticker: реальный тикер
            record: запись {year, price, dividend, yoy_change, ...}
        """
        logger.debug(
            "Anonymizer.anonymize_record: заглушка, запись не анонимизирована: %r",
            real_ticker,
        )
        return {**record, "ticker": real_ticker}

    def anonymize_ticker_data(
        self,
        ticker_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        TODO (v0.3): анонимизировать полный объект {ticker, records: [...]}.

        Сейчас возвращает объект без изменений (pass-through).
        """
        logger.debug(
            "Anonymizer.anonymize_ticker_data: заглушка, данные не анонимизированы: %r",
            ticker_data.get("ticker"),
        )
        return ticker_data

    def anonymize_all(
        self,
        tickers_data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        TODO (v0.3): анонимизировать список тикеров.

        Сейчас возвращает список без изменений (pass-through).
        """
        logger.debug(
            "Anonymizer.anonymize_all: заглушка, %d тикеров не анонимизированы",
            len(tickers_data),
        )
        return tickers_data

    def __repr__(self) -> str:
        return (
            f"Anonymizer("
            f"strategy={self._strategy.__class__.__name__!r}, "
            f"map_size={len(self._map)})"
        )


# ─────────────────────────── DeAnonymizer ─────────────────────────

class DeAnonymizer:
    """
    Деанонимизирует результаты агентов — восстанавливает реальные тикеры.

    TODO (v0.3):
        - Реализовать deanonymize_ticker()
        - Реализовать deanonymize_result()
        - Реализовать deanonymize_results()
    """

    def __init__(self, map_: AnonymizationMap) -> None:
        """
        Args:
            map_: карта анонимизации от Anonymizer (та же сессия)
        """
        self._map = map_

    def deanonymize_ticker(self, anonymous_ticker: str) -> str:
        """
        TODO (v0.3): восстановить реальный тикер из анонимного.

        Сейчас возвращает anonymous_ticker без изменений (pass-through).

        Args:
            anonymous_ticker: анонимный ID (например "STOCK_0001")

        Returns:
            Сейчас: anonymous_ticker без изменений.
            После реализации: реальный тикер (например "AAPL").
        """
        logger.debug(
            "DeAnonymizer.deanonymize_ticker: заглушка, тикер не деанонимизирован: %r",
            anonymous_ticker,
        )
        return anonymous_ticker

    def deanonymize_result(
        self,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        TODO (v0.3): заменить поле 'ticker' на реальный тикер.

        Сейчас возвращает result без изменений (pass-through).
        """
        logger.debug(
            "DeAnonymizer.deanonymize_result: заглушка, результат не деанонимизирован"
        )
        return result

    def deanonymize_results(
        self,
        anon_results: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        TODO (v0.3): деанонимизировать полный словарь результатов оркестратора.

        Сейчас возвращает anon_results без изменений (pass-through).
        """
        logger.debug(
            "DeAnonymizer.deanonymize_results: заглушка, %d тикеров не деанонимизированы",
            len(anon_results),
        )
        return anon_results

    def __repr__(self) -> str:
        return f"DeAnonymizer(map_size={len(self._map)})"