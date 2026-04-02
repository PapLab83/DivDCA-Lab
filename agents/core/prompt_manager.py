"""
Prompt Manager — управление промптами агентов.

TODO (v0.2):
    - Загрузка промптов из YAML/Jinja2 шаблонов
    - Версионирование промптов
    - Подстановка переменных
    - Реализация PromptManagerProtocol из base_agent.py
"""

from agents.core.base_agent import PromptManagerProtocol


class PromptManager:
    """
    Менеджер промптов.

    Планируемый функционал:
        - get_prompt(task, **variables) -> (prompt, version)
        - загрузка шаблонов из файлов
        - A/B тестирование промптов
    """

    def get_prompt(self, task: str, **variables) -> tuple[str, str]:
        raise NotImplementedError(
            "PromptManager ещё не реализован. Планируется в v0.2."
        )