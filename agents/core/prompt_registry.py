"""
Prompt Registry — учёт версий промптов с Git-интеграцией.

Отвечает за:
- хранение истории версий (какой промпт когда был активен)
- получение текущего Git-коммита/тега как версии
- сравнение версий (diff между двумя записями)

Не отвечает за:
- сборку промптов из секций (это PromptManager)
- подстановку переменных (это PromptManager._render)

Использование:
    registry = PromptRegistry()
    registry.record("event_generation", "1.0.0", template)
    snapshot = registry.get_snapshot("event_generation")
    print(snapshot.git_commit)   # abc1234
    print(snapshot.version)      # 1.0.0
"""

__all__ = [
    "PromptSnapshot",
    "PromptRegistry",
]

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────── Git helpers ──────────────────────────

def _get_git_commit(short: bool = True) -> Optional[str]:
    """
    Возвращает текущий Git-коммит.

    Args:
        short: True → короткий хэш (7 символов), False → полный

    Returns:
        Строка коммита или None если git недоступен / не git-репозиторий
    """
    fmt = "--short" if short else ""
    cmd = ["git", "rev-parse", fmt, "HEAD"] if fmt else ["git", "rev-parse", "HEAD"]
    cmd = [c for c in cmd if c]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        logger.debug("git rev-parse вернул код %d: %s", result.returncode, result.stderr.strip())
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug("git недоступен: %s", e)
        return None


def _get_git_tag() -> Optional[str]:
    """
    Возвращает ближайший Git-тег для HEAD.

    Returns:
        Строка тега (например 'v1.2.0') или None
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _get_git_branch() -> Optional[str]:
    """Возвращает текущую Git-ветку."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


# ─────────────────────────── Snapshot ─────────────────────────────

@dataclass(frozen=True)
class PromptSnapshot:
    """
    Снимок состояния промпта в момент регистрации.

    Attributes:
        task: идентификатор задачи
        version: версия из PromptTemplate
        recorded_at: момент регистрации (UTC)
        git_commit: короткий хэш коммита (None если git недоступен)
        git_tag: тег релиза (None если нет тега на HEAD)
        git_branch: ветка (None если git недоступен)
        sections_hash: хэш содержимого секций для детектирования изменений
        sections_count: количество секций в промпте
    """
    task: str
    version: str
    recorded_at: datetime
    git_commit: Optional[str]
    git_tag: Optional[str]
    git_branch: Optional[str]
    sections_hash: str
    sections_count: int

    def identity(self) -> str:
        """
        Строковый идентификатор снимка для логов и сравнения.
        Формат: task@version#commit (или task@version если git недоступен)
        """
        commit_part = f"#{self.git_commit}" if self.git_commit else ""
        tag_part = f"[{self.git_tag}]" if self.git_tag else ""
        return f"{self.task}@{self.version}{commit_part}{tag_part}"

    def __str__(self) -> str:
        return (
            f"PromptSnapshot("
            f"task={self.task!r}, "
            f"version={self.version!r}, "
            f"commit={self.git_commit!r}, "
            f"tag={self.git_tag!r}, "
            f"branch={self.git_branch!r}, "
            f"recorded_at={self.recorded_at.isoformat()}"
            f")"
        )


# ─────────────────────────── Registry ─────────────────────────────

class PromptRegistry:
    """
    Реестр версий промптов с Git-интеграцией.

    Хранит историю всех зарегистрированных промптов.
    Позволяет получить текущий снимок и полную историю изменений.

    Git-метаданные (commit, tag, branch) захватываются ОДИН РАЗ
    при инициализации PromptRegistry — не при каждом record().
    Это исключает N subprocess-вызовов при регистрации N промптов.

    Использование совместно с PromptManager:
        manager = PromptManager()
        registry = PromptRegistry()

        manager.register("event_generation", template)
        registry.record_from_template("event_generation", template)

        snapshot = registry.get_snapshot("event_generation")
        print(snapshot.identity())  # event_generation@1.0.0#abc1234
    """

    def __init__(self, capture_git: bool = True) -> None:
        """
        Args:
            capture_git: захватывать Git-метаданные при инициализации.
                False полезен в тестах или CI без git.
        """
        self._capture_git = capture_git
        self._history: Dict[str, List[PromptSnapshot]] = {}
        if capture_git:
            self._git_commit: Optional[str] = _get_git_commit()
            self._git_tag: Optional[str] = _get_git_tag()
            self._git_branch: Optional[str] = _get_git_branch()
            logger.debug(
                "PromptRegistry: Git-состояние захвачено: commit=%s, tag=%s, branch=%s",
                self._git_commit, self._git_tag, self._git_branch,
            )
        else:
            self._git_commit = None
            self._git_tag = None
            self._git_branch = None

    # ── Запись ────────────────────────────────────────────────────

    def record(
        self,
        task: str,
        version: str,
        sections: Dict[str, str],
    ) -> PromptSnapshot:
        """
        Записывает снимок промпта.

        Args:
            task: идентификатор задачи
            version: версия промпта (из PromptTemplate.version)
            sections: словарь секций промпта (для вычисления хэша)

        Returns:
            Созданный PromptSnapshot
        """
        sections_hash = self._hash_sections(sections)

        snapshot = PromptSnapshot(
            task=task,
            version=version,
            recorded_at=datetime.now(timezone.utc),
            git_commit=self._git_commit,
            git_tag=self._git_tag,
            git_branch=self._git_branch,
            sections_hash=sections_hash,
            sections_count=len(sections),
        )

        if task not in self._history:
            self._history[task] = []

        # Не дублируем если содержимое не изменилось
        if self._history[task]:
            last = self._history[task][-1]
            if last.sections_hash == sections_hash and last.version == version:
                logger.debug(
                    "PromptRegistry: пропущена запись '%s' — содержимое не изменилось",
                    task,
                )
                return last

        self._history[task].append(snapshot)
        logger.info(
            "PromptRegistry: записан %s",
            snapshot.identity(),
        )
        return snapshot

    def record_from_template(self, task: str, template) -> PromptSnapshot:
        """
        Удобный метод для записи напрямую из PromptTemplate.

        Args:
            task: идентификатор задачи
            template: экземпляр PromptTemplate

        Returns:
            Созданный PromptSnapshot
        """
        return self.record(
            task=task,
            version=template.version,
            sections=template.sections,
        )

    # ── Чтение ────────────────────────────────────────────────────

    def get_snapshot(self, task: str) -> Optional[PromptSnapshot]:
        """Возвращает последний снимок для задачи или None."""
        history = self._history.get(task, [])
        return history[-1] if history else None

    def get_history(self, task: str) -> List[PromptSnapshot]:
        """Возвращает полную историю снимков для задачи."""
        return list(self._history.get(task, []))

    def list_tasks(self) -> List[str]:
        """Список задач с хотя бы одним снимком."""
        return list(self._history.keys())

    def has_changes(self, task: str, template) -> bool:
        """
        Проверяет, изменился ли промпт относительно последнего снимка.

        Полезно для детектирования незафиксированных изменений промптов.

        Args:
            task: идентификатор задачи
            template: текущий PromptTemplate для сравнения

        Returns:
            True если содержимое изменилось или снимка нет
        """
        snapshot = self.get_snapshot(task)
        if snapshot is None:
            return True
        current_hash = self._hash_sections(template.sections)
        return snapshot.sections_hash != current_hash

    def format_report(self) -> str:
        """Human-readable отчёт по всем зарегистрированным промптам."""
        if not self._history:
            return "PromptRegistry: нет зарегистрированных промптов"

        lines = ["PromptRegistry — текущие версии:"]
        for task, history in self._history.items():
            last = history[-1]
            lines.append(
                f"  {task}: {last.identity()} "
                f"(секций: {last.sections_count}, "
                f"изменений: {len(history)})"
            )
        return "\n".join(lines)

    # ── Приватные ─────────────────────────────────────────────────

    @staticmethod
    def _hash_sections(sections: Dict[str, str]) -> str:
        """
        Вычисляет хэш содержимого секций.
        Порядок ключей нормализован для стабильности.
        """
        import hashlib
        combined = "|".join(
            f"{k}:{v}"
            for k, v in sorted(sections.items())
        )
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

    def __repr__(self) -> str:
        return (
            f"PromptRegistry("
            f"tasks={self.list_tasks()!r}, "
            f"capture_git={self._capture_git!r}, "
            f"commit={self._git_commit!r})"
        )