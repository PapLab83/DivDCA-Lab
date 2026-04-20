# 1. ARCHITECTURE.md (переписан полностью)

```markdown
# Architecture

## Vision

Мультиагентная система — ядро финансового AI-консультанта.

**Цель продукта:** персональный консультант по долгосрочным инвестициям в акции
(преимущественно дивидендные), выдающий рекомендации по покупке/удержанию/продаже.

**Ключевые принципы:**

* **Обезличенные данные** — данные хранятся в БД уже анонимизированными.
  Тикеры заменены на анонимные идентификаторы на уровне базы данных.
  Pipeline и агенты работают исключительно с обезличенными данными —
  никакой логики анонимизации в коде приложения нет и не нужно.
* **Адаптивная агрессивность** — базовые (консервативные) настройки для обычных
  пользователей, расширенные параметры риска для продвинутых
* **Расширяемость** — архитектура агентов не привязана к конкретной задаче;
  новые типы анализа добавляются как task-модули без изменения ядра
* **Провайдер-агностичность** — единый интерфейс к OpenAI, Claude, Gemini.
  Смена провайдера — одна переменная окружения

---

## Концептуальная модель

```text
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACE                        │
│         (API / Chat / Dashboard — будущее)               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│               ORCHESTRATOR (будущее)                     │
│  Маршрутизация запросов, управление стратегией,          │
│  профиль пользователя (conservative ↔ aggressive)        │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┼────────────┬──────────────┐
          ▼            ▼            ▼              ▼
     ┌─────────┐ ┌──────────┐ ┌─────────┐  ┌───────────┐
     │ Agent A │ │ Agent B  │ │ Agent C │  │ Agent ... │
     │ (event  │ │ (scoring)│ │(consens)│  │ (любой    │
     │  gen)   │ │          │ │         │  │  новый)   │
     └────┬────┘ └────┬─────┘ └────┬────┘  └─────┬─────┘
          │           │            │              │
          ▼           ▼            ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                    CORE FRAMEWORK                        │
│  BaseAgent · Factory · Registry · Validator · Skills     │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                     LLM LAYER                            │
│  LLMAdapter · Retry · Cache · Engines (OpenAI/Claude/…) │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                     DATA LAYER                           │
│  Обезличенные исторические данные · Feature store        │
│                                                          │
│  ⚠️  Анонимизация выполнена на уровне БД.               │
│  Приложение получает уже обезличенные данные.            │
│  Никакого маппинга тикер↔ID в коде приложения нет.      │
└─────────────────────────────────────────────────────────┘
```

---

## Обезличивание данных

Анонимизация — **ответственность слоя данных**, не приложения.

```text
Реальные данные          БД (анонимизировано)        Приложение
┌──────────────┐         ┌──────────────────┐        ┌──────────────────┐
│ AAPL, $150   │  ETL /  │ STOCK_0042, $150 │ ──────▶│ STOCK_0042, $150 │
│ div yield 2% │ ──────▶ │ div yield 2%     │        │ div yield 2%     │
│ sector: Tech │ import  │ sector: A        │        │ sector: A        │
└──────────────┘         └──────────────────┘        └──────────────────┘
                                                              │
                                                              ▼
                                                      ┌──────────────┐
                                                      │  LLM / Agent │
                                                      └──────────────┘
```

**Что это даёт:**
- LLM не знает реальных тикеров → не может «вспомнить» исторические данные
  из обучающей выборки (предотвращение data leakage)
- Код приложения не содержит логики анонимизации — нет риска случайной утечки
- Маппинг `реальный тикер ↔ анонимный ID` хранится только в БД,
  недоступен агентам

**Следствие для разработки:**
- `mock_data.py` использует условные тикеры (AAPL, JNJ, T) только для удобства
  разработки и тестирования
- В production pipeline данные приходят из БД уже обезличенными
- Pipeline и агенты не делают никаких предположений о формате идентификатора

---

## Профили агрессивности

```text
Conservative (default)          Aggressive (advanced user)
├── div yield ≥ 3%              ├── div yield ≥ 0%
├── volatility ≤ 15%            ├── volatility ≤ 40%
├── hold period ≥ 5y            ├── hold period ≥ 1y
├── max portfolio share ≤ 5%    ├── max portfolio share ≤ 20%
└── confidence threshold ≥ 0.8  └── confidence threshold ≥ 0.5
```

Профиль передаётся в контекст агента и влияет на:

* формирование промптов (constraints в system prompt)
* фильтрацию результатов (post-processing через ProfileValidator)
* пороги принятия решений

---

## Структура проекта

```text
agents/
├── core/                              # ── Ядро (framework) ──
│   ├── types.py                       # Shared типы, Protocol'ы — единый источник правды
│   ├── base_agent.py                  # BaseAgent + re-export типов из types.py
│   ├── agent_factory.py               # Фабрика создания агентов
│   ├── agent_registry.py              # Реестр метаданных (inputs/outputs/version)
│   ├── agent_validator.py             # Валидация совместимости агент ↔ конфиг
│   ├── agent_lifecycle.py             # Жизненный цикл (таймер, финализация, логи)
│   ├── response_parser.py             # Парсинг и валидация ответов LLM
│   ├── error_mapper.py                # Маппинг исключений → AgentResult
│   ├── container.py                   # DI-контейнер (сборка всех зависимостей)
│   ├── prompt_manager.py              # Сборка промптов из секций, YAML, версионирование
│   ├── prompt_registry.py             # Git-версионирование промптов
│   │
│   ├── profiles/                      # ── Профили пользователя ──
│   │   ├── profile.py                 # UserProfile, ProfileConfig, AggressivenessLevel
│   │   └── profile_validator.py       # Фильтрация результатов по профилю
│   │
│   ├── llm/                           # ── LLM-слой ──
│   │   ├── adapter.py                 # LLMAdapter — единый интерфейс + cache + retry
│   │   ├── exceptions.py              # Иерархия исключений (single source of truth)
│   │   └── engines/                   # Провайдер-специфичные реализации
│   │       ├── base_engine.py         # Абстрактный BaseLLMEngine (sync + async + stream)
│   │       ├── openai_compatible.py   # Универсальный OpenAI-совместимый engine
│   │       ├── openai_engine.py       # OpenAI (GPT-4, GPT-4o)
│   │       ├── claude_engine.py       # Anthropic Claude (через OpenAI-compatible прокси)
│   │       └── gemini_engine.py       # Google Gemini (через OpenAI-compatible прокси)
│   │
│   ├── skills/                        # ── Переиспользуемые навыки ──
│   │   ├── cache.py                   # InMemoryCache (LRU, thread-safe)
│   │   ├── file_storage.py            # [TODO v0.2] Персистентное хранение
│   │   └── json_validator.py          # [TODO v0.2] Валидация JSON-схем ответов
│   │
│   └── tools/                         # ── Инструменты агентов ──
│       ├── base_tool.py               # Базовый интерфейс инструмента
│       ├── calculation_tool.py        # [TODO v0.2] Финансовые расчёты (DCF, div yield)
│       ├── db_tool.py                 # [TODO v0.2] Доступ к данным
│       └── etl_tool.py                # [TODO v0.2] Загрузка и трансформация данных
│
├── tasks/                             # ── Конкретные агенты-задачи ──
│   ├── event_generation/
│   │   └── agent.py                   # EventGenerationAgent — объясняет изменения дивидендов
│   ├── event_scoring/
│   │   └── agent.py                   # [TODO v0.2] Оценка значимости событий
│   ├── consensus/
│   │   └── agent.py                   # [TODO v0.3] Консенсус между агентами
│   └── financial_analysis/            # [TODO v0.3] Комплексный финансовый анализ
│
├── prompts/
│   └── event_generation.yaml          # Промпт для EventGenerationAgent
│
├── config.py                          # Загрузка конфигурации (env → YAML → defaults)
└── tests/
    ├── conftest.py                    # Общие фикстуры
    └── test_core.py                   # Тесты ядра

mas/
├── price_drivers_collection/
│   ├── mock_data.py                   # Тестовые данные (условные тикеры для разработки)
│   ├── pipeline.py                    # Обработка одного тикера за период
│   ├── orchestrator.py                # Координация обработки всех тикеров
│   └── run.py                         # Точка входа
└── tests/
    ├── conftest.py                    # Фикстуры pipeline-слоя
    ├── test_mock_data.py
    ├── test_pipeline.py
    └── test_orchestrator.py
```

---

## Ключевые паттерны

### Dependency Injection через Protocol

```text
BaseAgent ──depends on──▶ LLMAdapterProtocol    (контракт)
                          CacheProtocol          (контракт)
                          PromptManagerProtocol  (контракт)
                                │
                    конкретные реализации инжектируются
                    через Container ↓
                                │
                          LLMAdapter · InMemoryCache · PromptManager
```

Агент не знает о конкретном провайдере — работает через протоколы.
Подмена LLM на mock в тестах — без изменения кода агента.

---

### Поток выполнения агента

```text
execute(context)
  │
  ├── _enrich_context_with_profile()   # добавляет UserProfile в metadata (если задан)
  ├── _setup(context)                  # hook: подготовка
  │
  ├── _execute_internal(context)       # abstract: бизнес-логика наследника
  │     ├── _get_prompt(context)       #   PromptManager → (prompt, version)
  │     ├── _call_llm(prompt)          #   LLMAdapter → raw response
  │     └── _parse_response(raw)       #   ResponseParser: JSON + required_fields
  │
  ├── _handle_error(exception)         # ErrorMapper: graceful degradation
  │
  ├── _cleanup(context)                # hook: очистка ресурсов
  │
  └── return AgentResult               # frozen dataclass
        ├── success: bool
        ├── data: dict
        ├── duration_ms: int
        ├── tokens_used: int
        └── prompt_version: str
```

---

### LLM-слой

```text
LLMAdapter
  ├── cache check (InMemoryCache / CacheProtocol)
  ├── retry logic (tenacity: exponential backoff, только LLMTransientError)
  └── engine dispatch (instance-level registry, изолирован между экземплярами)
        │
        ▼
  BaseLLMEngine (abstract)
    ├── OpenAICompatibleEngine        # sync + async + stream
    │     ├── OpenAIEngine            # GPT-4, GPT-4o
    │     ├── ClaudeEngine            # Anthropic (через OpenAI-compatible прокси)
    │     └── GeminiEngine            # Google (через OpenAI-compatible прокси)
    └── MockEngine                    # для тестов, без внешних вызовов
```

---

### Иерархия исключений

```text
LLMEngineError (базовая)
  ├── LLMTransientError (retry-able)
  │     ├── LLMConnectionError       # сеть недоступна
  │     ├── LLMRateLimitError        # 429 Too Many Requests
  │     └── LLMTimeoutError          # таймаут запроса
  ├── LLMAuthenticationError         # невалидный API-ключ (не retry)
  ├── LLMInvalidRequestError         # некорректный промпт (не retry)
  └── LLMParseError                  # ответ не парсится как JSON (не retry)
```

---

### Создание агентов

```text
Container
  │ собирает: config → cache → llm_adapter → prompt_manager
  │           registry → validator → factory(с defaults)
  │
  ▼
AgentFactory                          AgentRegistry
  │ хранит: type → Class (через reg.) │ хранит: type → Metadata
  │                                   │   (name, version, inputs, outputs)
  ▼                                   ▼
factory.create_agent(type, config)
  │
  ├── registry.get_class(type)        # получить класс
  ├── validator.validate(type, config) # проверить совместимость
  └── AgentClass(config, llm, pm)     # создать с инжектированными зависимостями
```

---

### Pipeline (mas)

```text
run.py
  │
  ├── build_container()               # DI-контейнер
  ├── load_data(source)               # данные из БД (уже обезличены) или mock
  ├── load_profile(level)             # UserProfile из ENV
  │
  └── run_collection(container, data, profile)   # orchestrator
        │
        └── для каждого тикера:
              process_ticker(container, ticker, records, profile)
                │
                └── для каждого года:
                      _call_agent_with_timeout(agent, context, timeout, executor)
                            │
                            └── agent.execute(context) → AgentResult
```

---

## Конфигурация

Приоритет: **аргументы функции → ENV vars → YAML файл → defaults в коде**

| Переменная        | Описание                                                               | Default       |
| ----------------- | ---------------------------------------------------------------------- | ------------- |
| `LLM_PROVIDER`    | openai / claude / gemini / mock                                        | mock          |
| `LLM_MODEL`       | Название модели                                                        | gpt-4         |
| `LLM_TEMPERATURE` | Креативность (0.0–2.0)                                                 | 0.7           |
| `LLM_MAX_TOKENS`  | Макс. токенов ответа                                                   | 1000          |
| `LLM_TIMEOUT`     | Таймаут LLM запроса (сек)                                              | 30            |
| `API_KEY`         | API ключ (fallback: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY) | —             |
| `API_BASE_URL`    | Кастомный endpoint (обязателен для Claude/Gemini)                      | —             |
| `API_RETRIES`     | Количество повторов при LLMTransientError                              | 3             |
| `DATA_SOURCE`     | Источник данных: mock / db / csv / api                                 | mock          |
| `USER_PROFILE`    | conservative / moderate / aggressive                                   | conservative  |

---

## Статус реализации

| Компонент                                          | Статус | Приоритет |
| -------------------------------------------------- | :----: | :-------: |
| BaseAgent + execute (sync/async)                   |   ✅   |     —     |
| AgentFactory (thread-safe, через Container)        |   ✅   |     —     |
| AgentRegistry (metadata, YAML)                     |   ✅   |     —     |
| AgentValidator                                     |   ✅   |     —     |
| AgentLifecycle / ResponseParser / ErrorMapper      |   ✅   |     —     |
| LLMAdapter + retry + cache                         |   ✅   |     —     |
| OpenAI-compatible engines                          |   ✅   |     —     |
| Exception hierarchy                                |   ✅   |     —     |
| InMemoryCache (LRU)                                |   ✅   |     —     |
| Config loading (env + YAML)                        |   ✅   |     —     |
| PromptManager (секции, YAML, версионирование)      |   ✅   |     —     |
| PromptRegistry (Git-интеграция)                    |   ✅   |     —     |
| UserProfile + ProfileValidator                     |   ✅   |     —     |
| EventGenerationAgent                               |   ✅   |     —     |
| Pipeline + Orchestrator (mas)                      |   ✅   |     —     |
| Тесты (core + mas pipeline)                        |   ✅   |     —     |
| EventScoringAgent                                  |   ⬜   |    P1     |
| ConsensusAgent                                     |   ⬜   |    P2     |
| Tools (calculation, DB, ETL)                       |   ⬜   |    P2     |
| Skills (file storage, JSON schema)                 |   ⬜   |    P2     |
| DB data source (production pipeline)               |   ⬜   |    P1     |
| Orchestrator (multi-agent routing)                 |   ⬜   |    P2     |
| UI / API layer                                     |   ⬜   |    P3     |
```