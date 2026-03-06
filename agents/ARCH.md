```
agents/
├── __init__.py
├── collect_code.py (10.9 KB) - # Утилита для сбора кода проекта
├── orchestrator.py (76 B) - # Оркестратор: координация всего процесса
├── pipeline.py (64 B) - # Полный пайплайн для одного тикера
│
├── core/
│   ├── __init__.py
│   ├── base_agent.py (66 B) - # Абстрактный класс для всех агентов
│   ├── prompt_manager.py (0 B)
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── adapter.py (68 B) - # LLMAdapter - единый интерфейс для агентов
│   │   ├── factory.py (0 B)
│   │   │
│   │   └── engines/
│   │       ├── __init__.py
│   │       ├── base_engine.py (0 B)
│   │       ├── claude_engine.py (0 B)
│   │       ├── gemini_engine.py (0 B)
│   │       └── openai_engine.py (0 B)
│   │
│   └── skills/
│       ├── __init__.py
│       ├── base_skill.py (0 B)
│       ├── cache.py (0 B)
│       ├── file_storage.py (0 B)
│       └── json_validator.py (0 B)
│
├── tasks/
│   ├── __init__.py
│   │
│   ├── event_generation/
│   │   ├── __init__.py
│   │   └── agent.py (0 B)
│   │
│   ├── event_validation/
│   │   ├── __init__.py
│   │   └── agent.py (0 B)
│   │
│   └── financial_analysis/
│       ├── __init__.py
│       └── (agent.py отсутствует)
│
└── consensus/
    ├── __init__.py
    ├── engine.py (53 B) - # ConsensusEngine - сравнение событий
    └── models.py (65 B) - # Модели для результатов консенсуса
```

### Краткое описание основных файлов (в порядке архитектурной иерархии)

| Уровень | Путь | Размер | Назначение |
|---------|------|--------|------------|
| **Точки входа** | `pipeline.py` | 64 B | Полный конвейер обработки для одного тикера — основной строительный блок |
| | `orchestrator.py` | 76 B | Координатор, управляющий последовательностью работы всех агентов |
| | `collect_code.py` | 10.9 KB | Утилита для сбора и консолидации кода проекта (не относится к логике агентов) |
| **Ядро (core)** | `core/base_agent.py` | 66 B | Абстрактный базовый класс, от которого наследуются все конкретные агенты |
| | `core/llm/adapter.py` | 68 B | Единый интерфейс для работы с разными LLM (OpenAI, Claude, Gemini) |
| | `core/llm/factory.py` | 0 B | Фабрика для создания движков конкретных LLM-провайдеров |
| | `core/llm/engines/` | - | Движки для каждого провайдера (base, claude, gemini, openai) |
| | `core/prompt_manager.py` | 0 B | Управление промптами (версионирование, шаблоны) |
| | `core/skills/` | - | Набор переиспользуемых навыков (кэш, валидация JSON, работа с файлами) |
| **Задачи (tasks)** | `tasks/event_generation/agent.py` | 0 B | Агент, генерирующий описания событий (причины роста/падения) |
| | `tasks/event_validation/agent.py` | 0 B | Агент, проверяющий и валидирующий сгенерированные описания |
| | `tasks/financial_analysis/` | - | Зарезервировано для будущих агентов финансового анализа |
| **Консенсус** | `consensus/engine.py` | 53 B | Механизм сравнения и синтеза результатов от разных агентов |
| | `consensus/models.py` | 65 B | Pydantic модели для результатов консенсуса |

### Управление промптами (Prompt Manager)

```
agents/tasks/event_generation/
├── agent.py
└── prompts/
    ├── constraints.txt      # ограничения (что нельзя делать)
    ├── examples.txt         # примеры хороших ответов
    ├── format.txt           # требуемый формат вывода (JSON, структура)
    ├── instruction.txt      # основная инструкция (что нужно сделать)
    └── system.txt           # системный промпт (роль агента)
```