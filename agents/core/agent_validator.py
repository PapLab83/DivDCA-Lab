"""
Валидатор совместимости агента с конфигурацией.
Единственная ответственность — проверка ограничений.
"""

__all__ = [
    "ValidationError",
    "ValidationResult",
    "AgentValidator",
]

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from agents.core.base_agent import AgentConfig
from agents.core.agent_registry import AgentRegistry, AgentMetadata


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationError:
    """Структурированная ошибка с кодом и сообщением."""
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Результат валидации."""
    is_valid: bool
    errors: Tuple[ValidationError, ...] = ()

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(is_valid=True)

    @classmethod
    def fail(cls, *errors: ValidationError) -> "ValidationResult":
        return cls(is_valid=False, errors=errors)

    def __str__(self) -> str:
        if self.is_valid:
            return "ValidationResult: OK"
        preview = self.errors[:3]
        suffix = f" ... and {len(self.errors) - 3} more" if len(self.errors) > 3 else ""
        errors_str = "; ".join(e.code for e in preview)
        return f"ValidationResult: FAILED ({len(self.errors)} errors) [{errors_str}{suffix}]"

    def __repr__(self) -> str:
        return (
            f"ValidationResult("
            f"is_valid={self.is_valid!r}, "
            f"errors={self.errors!r})"
        )


class AgentValidator:
    """Проверяет, может ли агент работать с заданной конфигурацией."""

    __slots__ = ("_registry",)

    def __init__(self, registry: AgentRegistry):
        self._registry = registry

    def validate(self, agent_type: str, config: AgentConfig) -> ValidationResult:
        """Полная проверка: провайдер + наличие в реестре."""
        if not isinstance(agent_type, str) or not agent_type.strip():
            return ValidationResult.fail(
                ValidationError(
                    code="INVALID_AGENT_TYPE",
                    message=f"agent_type is empty or not a string: {agent_type!r}",
                )
            )

        if config is None or config.llm_config is None:
            return ValidationResult.fail(
                ValidationError(
                    code="CONFIG_MISSING",
                    message="config or config.llm_config is None",
                )
            )

        metadata = self._registry.get(agent_type)
        if metadata is None:
            logger.error("Agent '%s' not found in registry", agent_type)
            return ValidationResult.fail(
                ValidationError(
                    code="AGENT_NOT_FOUND",
                    message=f"Agent '{agent_type}' not found in registry",
                )
            )

        errors = self._collect_errors(agent_type, metadata, config)
        for err in errors:
            logger.warning("[%s] %s", err.code, err.message)
        return ValidationResult(is_valid=not errors, errors=tuple(errors))

    def _collect_errors(
            self,
            agent_type: str,
            metadata: AgentMetadata,
            config: AgentConfig,
    ) -> List[ValidationError]:
        """Собирает список ошибок валидации."""
        errors: List[ValidationError] = []
        errors.extend(self._check_provider(agent_type, metadata, config))
        return errors

    def _check_provider(
            self,
            agent_type: str,
            metadata: AgentMetadata,
            config: AgentConfig,
    ) -> List[ValidationError]:
        """
        Проверка совместимости провайдера.

        Семантика supported_providers:
            None  → поле не задано, проверка пропускается (любой разрешён)
            []    → ограничений нет, любой провайдер разрешён
            [...] → проверяем что провайдер из списка
        """
        # None → проверка не задана
        if metadata.supported_providers is None:
            return []

        # [] → ограничений нет, любой провайдер разрешён
        if not metadata.supported_providers:
            return []

        raw_provider = config.llm_config.provider
        if raw_provider is None:
            return [
                ValidationError(
                    code="PROVIDER_NOT_SET",
                    message=f"Agent '{agent_type}': provider is None",
                )
            ]

        normalized = self._normalize_provider(raw_provider)
        if normalized is None:
            return [
                ValidationError(
                    code="INVALID_PROVIDER_TYPE",
                    message=(
                        f"Agent '{agent_type}': expected str or StrEnum provider, "
                        f"got {type(raw_provider).__name__}: {raw_provider!r}"
                    ),
                )
            ]

        if normalized not in metadata.supported_providers:
            return [
                ValidationError(
                    code="PROVIDER_UNSUPPORTED",
                    message=(
                        f"Agent '{agent_type}' does not support provider '{normalized}'. "
                        f"Allowed: {metadata.supported_providers}"
                    ),
                )
            ]
        return []

    @staticmethod
    def _normalize_provider(raw_provider: object) -> Optional[str]:
        """
        Приводит провайдера к строке.

        LLMProvider наследует StrEnum который наследует str,
        поэтому isinstance(LLMProvider.OPENAI, str) → True.
        Явное str() гарантирует что возвращается чистая строка,
        а не объект LLMProvider — для надёжного сравнения с List[str].

        Возвращает строку если тип корректный,
        None если тип неожиданный.
        """
        if isinstance(raw_provider, str):
            return str(raw_provider)
        return None