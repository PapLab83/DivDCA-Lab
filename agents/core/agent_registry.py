class AgentRegistry:
    """
    Реестр всех доступных агентов.
    Хранит метаданные о каждом агенте: описание, версию, входные/выходные данные.
    """

    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Загружает информацию о стандартных агентах"""
        defaults = {
            'event_generation': {
                'name': 'Event Generation Agent',
                'description': 'Генерирует описания событий на основе исторических данных',
                'version': '0.1.0',
                'inputs': ['ticker', 'year', 'price', 'dividend', 'yoy_change'],
                'outputs': ['reason_short', 'reason_long', 'confidence'],
                'prompt_components': ['system', 'instruction', 'examples', 'format', 'constraints']
            },
            'event_validation': {
                'name': 'Event Validation Agent',
                'description': 'Проверяет и оценивает сгенерированные описания',
                'version': '0.1.0',
                'inputs': ['ticker', 'year', 'generated_text'],
                'outputs': ['score', 'feedback', 'suggestions'],
                'prompt_components': ['system', 'instruction', 'format']
            }
        }
        self._agents.update(defaults)

    def register(self, agent_type: str, metadata: Dict[str, Any]) -> None:
        """
        Регистрирует агента с метаданными.

        Args:
            agent_type: строковый идентификатор агента
            metadata: словарь с метаданными
        """
        self._agents[agent_type] = metadata
        logger.debug(f"Зарегистрированы метаданные для агента: {agent_type}")

    def get(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """Возвращает метаданные агента"""
        return self._agents.get(agent_type)

    def list_agents(self) -> List[str]:
        """Список всех зарегистрированных агентов"""
        return list(self._agents.keys())

    def get_info(self, agent_type: str) -> str:
        """Возвращает форматированную информацию об агенте"""
        if agent_type not in self._agents:
            return f"Агент '{agent_type}' не найден"

        info = self._agents[agent_type]
        lines = [
            f"Агент: {info.get('name', agent_type)}",
            f"Версия: {info.get('version', 'N/A')}",
            f"Описание: {info.get('description', 'Нет описания')}",
            f"Входные данные: {', '.join(info.get('inputs', []))}",
            f"Выходные данные: {', '.join(info.get('outputs', []))}",
        ]
        return "\n".join(lines)

    def validate_agent(self, agent_type: str, config: AgentConfig) -> bool:
        """
        Проверяет, может ли агент работать с заданной конфигурацией.
        """
        metadata = self.get(agent_type)
        if not metadata:
            return False

        # Проверяем, поддерживается ли провайдер
        if 'supported_providers' in metadata:
            if config.llm_config.provider.value not in metadata['supported_providers']:
                logger.warning(f"Агент {agent_type} не поддерживает провайдера {config.llm_config.provider}")
                return False

        return True
