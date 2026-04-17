"""
AnonymizerRegistry — реестр стратегий анонимизации.

Plugin pattern: новые стратегии регистрируются без изменения Anonymizer.

TODO (v0.3):
    - Реализовать register() с валидацией типа
    - Реализовать get() / get_or_default()
    - Подключить к Anonymizer через build_container() или явную передачу
"""
import logging
from typing import Dict, List, Optional

from agents.core.anonymizer import AnonymizationStrategy

logger = logging.getLogger(__name__)


class AnonymizerRegistry:
    """
    Реестр стратегий анонимизации.

    TODO (v0.3): реализовать хранение и выдачу стратегий по имени.
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, AnonymizationStrategy] = {}

    def register(
        self,
        name: str,
        strategy: AnonymizationStrategy,
    ) -> None:
        """
        TODO (v0.3): зарегистрировать стратегию под именем.

        Args:
            name: уникальное имя стратегии
            strategy: экземпляр стратегии
        """
        raise NotImplementedError(
            "AnonymizerRegistry.register не реализован. Планируется в v0.3."
        )

    def get(self, name: str) -> Optional[AnonymizationStrategy]:
        """
        TODO (v0.3): вернуть стратегию по имени или None.
        """
        raise NotImplementedError(
            "AnonymizerRegistry.get не реализован. Планируется в v0.3."
        )

    def get_or_default(self, name: str) -> AnonymizationStrategy:
        """
        TODO (v0.3): вернуть стратегию по имени или 'default'.
        """
        raise NotImplementedError(
            "AnonymizerRegistry.get_or_default не реализован. Планируется в v0.3."
        )

    def list_strategies(self) -> List[str]:
        """
        TODO (v0.3): список зарегистрированных стратегий.
        """
        raise NotImplementedError(
            "AnonymizerRegistry.list_strategies не реализован. Планируется в v0.3."
        )

    def __repr__(self) -> str:
        return f"AnonymizerRegistry(strategies={list(self._strategies.keys())!r})"