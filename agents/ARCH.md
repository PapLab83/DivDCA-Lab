```
agents/
├── __init__.py
├── collect_code.py (10.9 KB)      # Утилита для сбора кода проекта
├── orchestrator.py                 # Оркестратор: координация всего процесса
├── pipeline.py                     # Полный пайплайн для одного тикера
├── run.py                          # Точка входа для запуска и дебага
│
├── core/
│   ├── __init__.py
│   ├── base_agent.py               # Абстрактный класс для всех агентов
│   ├── agent_registry.py           # Реестр агентов: регистрация, поиск, валидация
│   ├── agent_factory.py            # Фабрика: создание агентов через реестр
│   ├── prompt_manager.py           # Загрузка и сборка промптов из файлов
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── adapter.py              # LLMAdapter - единый интерфейс для агентов
│   │   │
│   │   └── engines/
│   │       ├── __init__.py
│   │       ├── base_engine.py      # Абстрактный класс engine, контракт call()
│   │       ├── openai_engine.py    # OpenAI + совместимые (gptunnel) через base_url
│   │       ├── claude_engine.py    # Claude engine
│   │       └── gemini_engine.py    # Gemini engine
│   │
│   └── skills/
│       ├── __init__.py
│       ├── cache.py                # CacheSkill
│       └── json_validator.py       # JsonValidatorSkill
│
└── tasks/
    ├── __init__.py
    │
    ├── event_generation/
    │   ├── __init__.py
    │   ├── agent.py                # EventGenerationAgent - генерация событий по тикеру
    │   └── prompts/
    │       ├── 01_role.txt
    │       ├── 02_task.txt
    │       └── 03_output_format.txt
    │
    ├── event_scoring/
    │   ├── __init__.py
    │   ├── agent.py                # EventScoringAgent - оценка важности события
    │   └── prompts/
    │       ├── 01_role.txt
    │       ├── 02_task.txt
    │       └── 03_output_format.txt
    │
    ├── impact_analysis/
    │   ├── __init__.py
    │   ├── agent.py                # ImpactAnalysisAgent - анализ влияния на цену
    │   └── prompts/
    │       ├── 01_role.txt
    │       ├── 02_task.txt
    │       └── 03_output_format.txt
    │
    ├── consensus/
    │   ├── __init__.py
    │   ├── agent.py                # ConsensusAgent - финальное решение по сигналу
    │   └── prompts/
    │       ├── 01_role.txt
    │       ├── 02_task.txt
    │       └── 03_output_format.txt
    │
    └── risk_assessment/
        ├── __init__.py
        ├── agent.py                # RiskAssessmentAgent - оценка рисков позиции
        └── prompts/
            ├── 01_role.txt
            ├── 02_task.txt
            └── 03_output_format.txt
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