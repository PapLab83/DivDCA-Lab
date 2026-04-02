"""
Агент генерации событий.

TODO (v0.2):
    - Наследник BaseAgent
    - Генерация reason_short, reason_long, confidence
    - Промпт с историческими данными дивидендов
    - Интеграция с PromptManager
"""

# from agents.core.base_agent import BaseAgent, AgentContext, AgentResult
#
# class EventGenerationAgent(BaseAgent):
#     def _execute_internal(self, context):
#         prompt, version = self._get_prompt(context, ...)
#         response = self._call_llm(prompt)
#         data = self._parse_response(response)
#         return AgentResult(success=True, data=data, prompt_version=version)