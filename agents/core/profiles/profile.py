"""
UserProfile — профиль агрессивности пользователя.

Определяет параметры риска и фильтрации результатов агентов.

Из ARCHITECTURE.md:
    Conservative (default):
        div yield ≥ 3%, volatility ≤ 15%, hold ≥ 5y,
        max share ≤ 5%, confidence ≥ 0.8

    Aggressive (advanced):
        div yield ≥ 0%, volatility ≤ 40%, hold ≥ 1y,
        max share ≤ 20%, confidence ≥ 0.5
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AggressivenessLevel(StrEnum):
    """Уровень агрессивности инвестиционного профиля."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ProfileConfig:
    """
    Числовые параметры профиля.

    Attributes:
        min_dividend_yield: минимальная дивидендная доходность (%)
        max_volatility: максимальная волатильность (%)
        min_hold_years: минимальный горизонт удержания (лет)
        max_portfolio_share: максимальная доля одной позиции (%)
        min_confidence: минимальный порог уверенности агента [0, 1]
        allow_growth_stocks: допускать growth-акции (без дивидендов)
        max_drawdown: максимально допустимая просадка (%)
    """
    min_dividend_yield: float = 3.0
    max_volatility: float = 15.0
    min_hold_years: int = 5
    max_portfolio_share: float = 5.0
    min_confidence: float = 0.8
    allow_growth_stocks: bool = False
    max_drawdown: float = 20.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError(
                f"min_confidence должен быть в [0, 1], получено: {self.min_confidence}"
            )
        if self.min_dividend_yield < 0:
            raise ValueError(
                f"min_dividend_yield не может быть отрицательным: {self.min_dividend_yield}"
            )
        if self.max_volatility <= 0:
            raise ValueError(
                f"max_volatility должен быть положительным: {self.max_volatility}"
            )
        if self.min_hold_years < 0:
            raise ValueError(
                f"min_hold_years не может быть отрицательным: {self.min_hold_years}"
            )
        if not 0.0 < self.max_portfolio_share <= 100.0:
            raise ValueError(
                f"max_portfolio_share должен быть в (0, 100]: {self.max_portfolio_share}"
            )


@dataclass(frozen=True)
class UserProfile:
    """
    Профиль пользователя — уровень агрессивности + числовые параметры.

    Использование:
        # Готовые профили:
        profile = UserProfile.conservative()
        profile = UserProfile.moderate()
        profile = UserProfile.aggressive()

        # Кастомный:
        profile = UserProfile(
            level=AggressivenessLevel.CUSTOM,
            config=ProfileConfig(min_confidence=0.6, max_volatility=25.0),
        )

        # Применение к результату агента:
        validator = ProfileValidator(profile)
        passed = validator.filter_results(results)
    """
    level: AggressivenessLevel
    config: ProfileConfig
    description: str = ""

    # ── Фабричные методы ──────────────────────────────────────────

    @classmethod
    def conservative(cls) -> "UserProfile":
        """
        Консервативный профиль (default для новых пользователей).

        Высокая дивидендная доходность, низкая волатильность,
        длинный горизонт, высокий порог уверенности.
        """
        return cls(
            level=AggressivenessLevel.CONSERVATIVE,
            config=ProfileConfig(
                min_dividend_yield=3.0,
                max_volatility=15.0,
                min_hold_years=5,
                max_portfolio_share=5.0,
                min_confidence=0.8,
                allow_growth_stocks=False,
                max_drawdown=20.0,
            ),
            description=(
                "Консервативный профиль: высокая дивидендная доходность (≥3%), "
                "низкая волатильность (≤15%), горизонт ≥5 лет."
            ),
        )

    @classmethod
    def moderate(cls) -> "UserProfile":
        """
        Умеренный профиль — баланс между доходностью и риском.
        """
        return cls(
            level=AggressivenessLevel.MODERATE,
            config=ProfileConfig(
                min_dividend_yield=1.5,
                max_volatility=25.0,
                min_hold_years=3,
                max_portfolio_share=10.0,
                min_confidence=0.65,
                allow_growth_stocks=True,
                max_drawdown=30.0,
            ),
            description=(
                "Умеренный профиль: дивидендная доходность ≥1.5%, "
                "волатильность ≤25%, горизонт ≥3 лет."
            ),
        )

    @classmethod
    def aggressive(cls) -> "UserProfile":
        """
        Агрессивный профиль для продвинутых пользователей.

        Допускает growth-акции, высокую волатильность,
        короткий горизонт, низкий порог уверенности.
        """
        return cls(
            level=AggressivenessLevel.AGGRESSIVE,
            config=ProfileConfig(
                min_dividend_yield=0.0,
                max_volatility=40.0,
                min_hold_years=1,
                max_portfolio_share=20.0,
                min_confidence=0.5,
                allow_growth_stocks=True,
                max_drawdown=50.0,
            ),
            description=(
                "Агрессивный профиль: дивидендная доходность ≥0%, "
                "волатильность ≤40%, горизонт ≥1 год."
            ),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        """
        Создаёт профиль из словаря (например из YAML/JSON конфига).

        Args:
            data: {
                "level": "conservative" | "moderate" | "aggressive" | "custom",
                "config": {ProfileConfig fields},
                "description": "..."  # опционально
            }
        """
        level = AggressivenessLevel(data["level"])
        config_data = data.get("config", {})
        config = ProfileConfig(**config_data)
        return cls(
            level=level,
            config=config,
            description=data.get("description", ""),
        )

    # ── Методы ───────────────────────────────────────────────────

    def to_prompt_constraints(self) -> str:
        """
        Возвращает строку ограничений для подстановки в system prompt.

        Используется PromptManager для добавления профиля в промпт агента.

        Returns:
            Строка с ограничениями в формате для LLM
        """
        cfg = self.config
        lines = [
            f"Investment profile: {self.level.value.upper()}",
            f"- Minimum dividend yield: {cfg.min_dividend_yield}%",
            f"- Maximum volatility: {cfg.max_volatility}%",
            f"- Minimum hold period: {cfg.min_hold_years} years",
            f"- Maximum portfolio share: {cfg.max_portfolio_share}%",
            f"- Minimum confidence threshold: {cfg.min_confidence}",
            f"- Growth stocks allowed: {'yes' if cfg.allow_growth_stocks else 'no'}",
            f"- Maximum drawdown: {cfg.max_drawdown}%",
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализует профиль в словарь."""
        return {
            "level": self.level.value,
            "description": self.description,
            "config": {
                "min_dividend_yield": self.config.min_dividend_yield,
                "max_volatility": self.config.max_volatility,
                "min_hold_years": self.config.min_hold_years,
                "max_portfolio_share": self.config.max_portfolio_share,
                "min_confidence": self.config.min_confidence,
                "allow_growth_stocks": self.config.allow_growth_stocks,
                "max_drawdown": self.config.max_drawdown,
            },
        }

    def __str__(self) -> str:
        return (
            f"UserProfile({self.level.value}, "
            f"confidence≥{self.config.min_confidence}, "
            f"volatility≤{self.config.max_volatility}%)"
        )