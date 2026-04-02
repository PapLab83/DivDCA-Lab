"""
Prompt Manager — сборка промптов из компонентов с подстановкой переменных.

Промпт собирается из именованных секций (system, instruction, examples, format, constraints).
Шаблоны загружаются из YAML или регистрируются программно.
Переменные подставляются через str.format_map().

Реализует PromptManagerProtocol из base_agent.py.
"""
import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# ─────────────────────────── Модель данных ────────────────────────

@dataclass
class PromptTemplate:
    """
    Шаблон промпта для одной задачи.

    Attributes:
        task: идентификатор задачи (e.g. "event_generation")
        version: версия шаблона (для трекинга в AgentResult)
        sections: именованные секции промпта в порядке сборки
        section_order: порядок секций при сборке (если None — порядок из sections)
        separator: разделитель между секциями
    """
    task: str
    version: str
    sections: Dict[str, str]
    section_order: Optional[List[str]] = None
    separator: str = "\n\n"

    def ordered_sections(self) -> List[str]:
        """Возвращает имена секций в порядке сборки."""
        if self.section_order:
            return [s for s in self.section_order if s in self.sections]
        return list(self.sections.keys())


class PromptNotFoundError(KeyError):
    """Шаблон промпта не найден."""


# ─────────────────────────── PromptManager ────────────────────────

class PromptManager:
    """
    Менеджер промптов — сборка из секций с подстановкой переменных.

    Использование:
        pm = PromptManager()
        pm.register("event_generation", PromptTemplate(
            task="event_generation",
            version="1.0.0",
            sections={
                "system": "You are a financial analyst...",
                "instruction": "Analyze dividend history for {ticker}, year {year}.",
                "format": "Respond in JSON: {{\"reason_short\": ..., \"confidence\": ...}}",
            },
        ))

        prompt, version = pm.get_prompt(
            "event_generation",
            ticker="STOCK_0042",
            year=2020,
        )

    Загрузка из YAML:
        pm = PromptManager.from_yaml("prompts/")
    """

    def __init__(self) -> None:
        self._templates: Dict[str, PromptTemplate] = {}

    # ── Регистрация ───────────────────────────────────────────────

    def register(self, task: str, template: PromptTemplate) -> None:
        """Регистрирует шаблон промпта для задачи."""
        self._templates[task] = template
        logger.debug(
            "Зарегистрирован промпт: task=%s, version=%s, sections=%s",
            task, template.version, list(template.sections.keys()),
        )

    def unregister(self, task: str) -> None:
        """Удаляет шаблон."""
        if task not in self._templates:
            raise PromptNotFoundError(f"Промпт для задачи '{task}' не найден")
        del self._templates[task]

    # ── Основной метод (PromptManagerProtocol) ────────────────────

    def get_prompt(self, task: str, **variables: Any) -> Tuple[str, str]:
        """
        Собирает промпт из секций и подставляет переменные.

        Args:
            task: идентификатор задачи
            **variables: переменные для подстановки в шаблон

        Returns:
            (prompt, version) — собранный промпт и версия шаблона

        Raises:
            PromptNotFoundError: шаблон не найден
            KeyError: переменная не передана, но есть в шаблоне
        """
        template = self._templates.get(task)
        if template is None:
            available = list(self._templates.keys())
            raise PromptNotFoundError(
                f"Промпт для задачи '{task}' не найден. "
                f"Доступные: {available}"
            )

        # Сборка секций в порядке
        parts: List[str] = []
        for section_name in template.ordered_sections():
            raw = template.sections[section_name]
            rendered = self._render(raw, variables)
            parts.append(rendered)

        prompt = template.separator.join(parts)

        logger.debug(
            "Собран промпт: task=%s, version=%s, len=%d, vars=%s",
            task, template.version, len(prompt), list(variables.keys()),
        )
        return prompt, template.version

    # ── Получение отдельных секций (для кастомной сборки) ─────────

    def get_section(
        self,
        task: str,
        section: str,
        **variables: Any,
    ) -> str:
        """
        Возвращает одну отрендеренную секцию.
        Полезно когда агент хочет собрать промпт нестандартно.
        """
        template = self._templates.get(task)
        if template is None:
            raise PromptNotFoundError(f"Промпт для задачи '{task}' не найден")
        raw = template.sections.get(section)
        if raw is None:
            raise PromptNotFoundError(
                f"Секция '{section}' не найдена в задаче '{task}'. "
                f"Доступные: {list(template.sections.keys())}"
            )
        return self._render(raw, variables)

    # ── Информация ────────────────────────────────────────────────

    def list_tasks(self) -> List[str]:
        """Список зарегистрированных задач."""
        return list(self._templates.keys())

    def get_template(self, task: str) -> Optional[PromptTemplate]:
        """Возвращает копию шаблона (без мутации оригинала)."""
        template = self._templates.get(task)
        return deepcopy(template) if template else None

    def has_task(self, task: str) -> bool:
        return task in self._templates

    # ── Загрузка из YAML ──────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: str) -> "PromptManager":
        """
        Загружает шаблоны из YAML-файла или директории.

        Формат YAML-файла:
            event_generation:
              version: "1.0.0"
              separator: "\\n\\n"          # опционально
              section_order:               # опционально
                - system
                - instruction
                - format
              sections:
                system: "You are a financial analyst..."
                instruction: "Analyze {ticker} for year {year}."
                format: "Respond in JSON..."

        Если path — директория, загружает все .yaml/.yml файлы.
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML required for YAML prompts: pip install pyyaml"
            ) from None

        manager = cls()
        p = Path(path)

        if p.is_file():
            manager._load_yaml_file(p, yaml)
        elif p.is_dir():
            files = sorted(p.glob("*.yaml")) + sorted(p.glob("*.yml"))
            if not files:
                logger.warning("Нет YAML-файлов в директории: %s", path)
            for f in files:
                manager._load_yaml_file(f, yaml)
        else:
            raise FileNotFoundError(f"Путь не найден: {path}")

        logger.info(
            "PromptManager загружен: %d задач из %s",
            len(manager._templates), path,
        )
        return manager

    def load_yaml(self, path: str) -> None:
        """Дозагружает шаблоны из YAML (добавляет к существующим)."""
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML required: pip install pyyaml"
            ) from None

        self._load_yaml_file(Path(path), yaml)

    def _load_yaml_file(self, path: Path, yaml_module: Any) -> None:
        """Парсит один YAML-файл и регистрирует шаблоны."""
        data = yaml_module.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(
                f"Ожидался dict в {path}, получен {type(data).__name__}"
            )

        for task_name, task_data in data.items():
            if not isinstance(task_data, dict) or "sections" not in task_data:
                logger.warning(
                    "Пропущен невалидный шаблон '%s' в %s", task_name, path,
                )
                continue

            template = PromptTemplate(
                task=task_name,
                version=task_data.get("version", "0.0.0"),
                sections=task_data["sections"],
                section_order=task_data.get("section_order"),
                separator=task_data.get("separator", "\n\n"),
            )
            self.register(task_name, template)

    # ── Приватные методы ──────────────────────────────────────────

    @staticmethod
    def _render(template_str: str, variables: Dict[str, Any]) -> str:
        """
        Подставляет переменные в строку.

        Использует format_map с SafeDict:
        - {ticker} → подставляется
        - {{literal_braces}} → остаётся как {literal_braces}
        - {unknown} → остаётся как {unknown} (не падает)
        """
        safe = _SafeFormatDict(variables)
        return template_str.format_map(safe)

    def __repr__(self) -> str:
        tasks = self.list_tasks()
        return f"PromptManager(tasks={tasks})"


class _SafeFormatDict(dict):
    """
    Dict для str.format_map(), который не падает на отсутствующих ключах.
    Неизвестные {placeholders} остаются как есть.
    """

    def __missing__(self, key: str) -> str:
        logger.warning("Переменная '{%s}' не передана в промпт", key)
        return "{" + key + "}"