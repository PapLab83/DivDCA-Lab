"""
Пакет профилей агрессивности пользователя.

Профиль влияет на:
- формирование промптов (constraints в system prompt)
- фильтрацию результатов агентов (post-processing)
- пороги принятия решений

Использование:
    from agents.core.profiles import UserProfile, AggressivenessLevel

    profile = UserProfile.conservative()
    profile = UserProfile.aggressive()
    profile = UserProfile(level=AggressivenessLevel.CUSTOM, config=ProfileConfig(...))
"""
from agents.core.profiles.profile import (
    AggressivenessLevel,
    ProfileConfig,
    UserProfile,
)
from agents.core.profiles.profile_validator import ProfileValidator

__all__ = [
    "AggressivenessLevel",
    "ProfileConfig",
    "UserProfile",
    "ProfileValidator",
]