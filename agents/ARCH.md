```
project/
│
├── agents/                        # 🧠 Agent Framework (переиспользуемый слой)
│   ├── core/
│   │   ├── base_agent.py
│   │   ├── agent_registry.py
│   │   ├── agent_factory.py
│   │   └── prompt_manager.py
│   │
│   ├── llm/
│   │   ├── adapter.py
│   │   └── engines/
│   │       ├── base_engine.py
│   │       ├── openai_engine.py
│   │       ├── claude_engine.py
│   │       └── gemini_engine.py
│   │
│   ├── skills/
│   │   ├── cache.py
│   │   └── json_validator.py
│   │
│   ├── tools/                    # 🔌 абстракции внешнего мира
│   │   ├── base_tool.py
│   │   ├── etl_tool.py
│   │   ├── db_tool.py
│   │   └── calculation_tool.py
│   │
│   └── tasks/                    # 🤖 реализации агентов
│       ├── event_generation/
│       │   ├── agent.py
│       │   └── prompts/
│       │
│       └── event_scoring/
│           ├── agent.py
│           └── prompts/
│
│
├── mas/                          # ⚙️ Multi-Agent Systems (сценарии)
│   ├── scenario_a/
│   │   ├── orchestrator.py       # логика взаимодействия агентов
│   │   ├── pipeline.py           # пайплайн (опционально)
│   │   └── run.py                # точка входа
│   │
│   ├── scenario_b/               # появится позже
│   │   └── ...
│   │
│   └── shared/                  # (опционально)
│       ├── memory.py
│       └── schemas.py
│
│
├── data_platform/               # 📊 ETL / подготовка данных
│   ├── etl/
│   ├── loaders/
│   └── pipelines/
│
│
├── calculations/                # 📈 классические расчёты (без агентов)
│
├── db/                          # 🗄️ доступ к БД
│
├── config/
│
└── main.py (или entrypoints)

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