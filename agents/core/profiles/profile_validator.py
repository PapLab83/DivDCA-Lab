"""
ProfileValidator — фильтрация результатов агентов по профилю пользователя.

Применяет пороги из UserProfile к результатам pipeline:
- фильтрует результаты ниже min_confidence
- проверяет соответствие дивидендной доходности
- логирует причины отклонения

Использование:
    validator = ProfileValidator(UserProfile.conservative())
    passed, rejected = validator.split_results(results)

    # Или только фильтрация:
    passed = validator.filter_results(results)
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from agents.core.profiles.profile import UserProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilterReason:
    """Причина отклонения результата."""
    field: str
    expected: str
    actual: str

    def __str__(self) -> str:
        return f"{self.field}: expected {self.expected}, got {self.actual}"


@dataclass
class FilterResult:
    """
    Результат фильтрации одной записи.

    Attributes:
        record: исходная запись
        passed: прошла ли фильтрацию
        reasons: список причин отклонения (пуст если passed=True)
    """
    record: Dict[str, Any]
    passed: bool
    reasons: List[FilterReason]


class ProfileValidator:
    """
    Фильтрует результаты агентов по параметрам UserProfile.

    Проверяет:
        - confidence: result["data"]["confidence"] ≥ profile.config.min_confidence
        - dividend_yield: если есть в данных — проверяет min_dividend_yield
        - success: отклоняет неуспешные результаты (success=False)

    Расширяемость:
        Добавляй новые проверки через _check_* методы
        и регистрируй их в _collect_reasons().
    """

    def __init__(self, profile: UserProfile) -> None:
        """
        Args:
            profile: профиль пользователя с параметрами фильтрации
        """
        self._profile = profile

    @property
    def profile(self) -> UserProfile:
        return self._profile

    # ── Публичный интерфейс ───────────────────────────────────────

    def filter_results(
        self,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Возвращает только результаты, прошедшие фильтрацию.

        Args:
            results: список результатов pipeline

        Returns:
            Отфильтрованный список
        """
        passed, _ = self.split_results(results)
        return passed

    def split_results(
        self,
        results: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[FilterResult]]:
        """
        Разделяет результаты на прошедшие и отклонённые.

        Args:
            results: список результатов pipeline

        Returns:
            (passed_records, rejected_filter_results)
        """
        passed: List[Dict[str, Any]] = []
        rejected: List[FilterResult] = []

        for record in results:
            filter_result = self.validate_record(record)
            if filter_result.passed:
                passed.append(record)
            else:
                rejected.append(filter_result)
                logger.debug(
                    "ProfileValidator: отклонён %s/%s — %s",
                    record.get("ticker", "?"),
                    record.get("year", "?"),
                    "; ".join(str(r) for r in filter_result.reasons),
                )

        logger.info(
            "ProfileValidator [%s]: %d/%d прошли фильтрацию",
            self._profile.level.value,
            len(passed),
            len(results),
        )
        return passed, rejected

    def validate_record(self, record: Dict[str, Any]) -> FilterResult:
        """
        Валидирует одну запись результата.

        Args:
            record: одна запись из результатов pipeline

        Returns:
            FilterResult с флагом passed и списком причин отклонения
        """
        reasons = self._collect_reasons(record)
        return FilterResult(
            record=record,
            passed=len(reasons) == 0,
            reasons=reasons,
        )

    # ── Сбор причин отклонения ────────────────────────────────────

    def _collect_reasons(
        self,
        record: Dict[str, Any],
    ) -> List[FilterReason]:
        """Собирает все причины отклонения записи."""
        reasons: List[FilterReason] = []

        reason = self._check_success(record)
        if reason:
            reasons.append(reason)
            # Если агент упал — дальнейшие проверки не имеют смысла
            return reasons

        reason = self._check_confidence(record)
        if reason:
            reasons.append(reason)

        reason = self._check_dividend_yield(record)
        if reason:
            reasons.append(reason)

        return reasons

    def _check_success(
        self,
        record: Dict[str, Any],
    ) -> Optional[FilterReason]:
        """Проверяет что агент выполнился успешно."""
        if not record.get("success", False):
            return FilterReason(
                field="success",
                expected="True",
                actual=f"False (error: {record.get('error', 'unknown')})",
            )
        return None

    def _check_confidence(
        self,
        record: Dict[str, Any],
    ) -> Optional[FilterReason]:
        """Проверяет порог уверенности агента."""
        data = record.get("data") or {}
        confidence = data.get("confidence")

        if confidence is None:
            return None  # нет поля — не проверяем

        min_conf = self._profile.config.min_confidence
        if confidence < min_conf:
            return FilterReason(
                field="confidence",
                expected=f"≥{min_conf}",
                actual=str(confidence),
            )
        return None

    def _check_dividend_yield(
        self,
        record: Dict[str, Any],
    ) -> Optional[FilterReason]:
        """
        Проверяет дивидендную доходность если она есть в данных.

        Дивидендная доходность = dividend / price * 100.
        Поля берутся из record напрямую (не из data агента).
        """
        price = record.get("price") or 0
        dividend = record.get("dividend")

        if dividend is None or price <= 0:
            return None  # нет данных — не проверяем

        div_yield = (dividend / price) * 100
        min_yield = self._profile.config.min_dividend_yield

        if div_yield < min_yield:
            return FilterReason(
                field="dividend_yield",
                expected=f"≥{min_yield}%",
                actual=f"{div_yield:.2f}%",
            )
        return None

    def __repr__(self) -> str:
        return f"ProfileValidator(profile={self._profile})"