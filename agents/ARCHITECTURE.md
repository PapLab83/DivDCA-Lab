# Architecture

## Vision

Мультиагентная система — ядро финансового AI-консультанта.

**Цель продукта:** персональный консультант по долгосрочным инвестициям в акции
(преимущественно дивидендные), выдающий рекомендации по покупке/удержанию/продаже.

**Ключевые принципы:**

* **Обезличенные данные** — модель обучается на исторических данных без привязки к тикерам,
  чтобы исключить «подглядывание» в будущее (data leakage prevention)
* **Адаптивная агрессивность** — базовые (консервативные) настройки для обычных пользователей,
  расширенные параметры риска/агрессивности для продвинутых
* **Расширяемость** — архитектура агентов не привязана к конкретной задаче;
  новые типы анализа добавляются как task-модули без изменения ядра

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
│                  DATA LAYER (будущее)                    │
│  Обезличенные исторические данные · Feature store       │
│  Маппинг тикер→анонимный ID (изолирован от LLM)         │
└─────────────────────────────────────────────────────────┘
```

---

## Обезличивание данных

```text
Реальные данные                    Обезличенные данные
┌──────────────┐    Anonymizer     ┌──────────────────┐
│ AAPL, $150   │ ──────────────▶   │ STOCK_0042, $150 │
│ div yield 2% │                   │ div yield 2%     │
│ sector: Tech │                   │ sector: A        │
└──────────────┘                   └──────────────────┘
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │  LLM / Agent │  ← не знает что это Apple
                                   └──────────────┘
                                          │
                                          ▼
                                   ┌──────────────────┐
                                   │ Рекомендация по   │
                                   │ STOCK_0042        │
                                   └────────┬─────────┘
                                            │
                              De-anonymizer │
                                            ▼
                                   ┌──────────────────┐
                                   │ Рекомендация по   │
                                   │ AAPL для юзера    │
                                   └──────────────────┘
```

**Зачем:** LLM обладает знаниями о публичных компаниях. Если передать "AAPL, 2020",
модель может «вспомнить» что акция выросла в 2021 и дать нечестную рекомендацию.
Обезличивание заставляет модель опираться только на числовые паттерны.

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
* фильтрацию результатов (post-processing)
* пороги принятия решений

---

## Структура проекта

```text
agents/
├── core/                              # ── Ядро (framework) ──
│   ├── base_agent.py                  # BaseAgent, Protocol'ы, Config, Result
│   ├── agent_factory.py               # Фабрика создания агентов
│   ├── agent_registry.py              # Реестр метаданных (inputs/outputs/version)
│   ├── agent_validator.py             # Валидация совместимости агент ↔ конфиг
│   ├── prompt_manager.py              # [TODO] Шаблонизация и версионирование промптов
│   │
│   ├── llm/                           # ── LLM-слой ──
│   │   ├── adapter.py                 # LLMAdapter — единый интерфейс + cache + retry
│   │   ├── exceptions.py              # Иерархия исключений (single source of truth)
│   │   └── engines/                   # Провайдер-специфичные реализации
│   │       ├── base_engine.py         # Абстрактный BaseLLMEngine (sync + async + stream)
│   │       ├── openai_compatible.py   # Универсальный OpenAI-совместимый engine
│   │       ├── openai_engine.py       # OpenAI (GPT-4, GPT-4o)
│   │       ├── claude_engine.py       # Anthropic Claude
│   │       └── gemini_engine.py       # Google Gemini
│   │
│   ├── skills/                        # ── Переиспользуемые навыки ──
│   │   ├── cache.py                   # InMemoryCache (LRU, thread-safe)
│   │   ├── file_storage.py            # [TODO] Персистентное хранение
│   │   └── json_validator.py          # [TODO] Валидация JSON-схем ответов
│   │
│   └── tools/                         # ── Инструменты агентов ──
│       ├── base_tool.py               # [TODO] Базовый интерфейс инструмента
│       ├── calculation_tool.py        # [TODO] Финансовые расчёты (DCF, div yield)
│       ├── db_tool.py                 # [TODO] Доступ к данным
│       └── etl_tool.py                # [TODO] Загрузка и трансформация данных
│
├── tasks/                             # ── Конкретные агенты-задачи ──
│   ├── event_generation/              # [TODO] Генерация описаний рыночных событий
│   │   └── agent.py
│   ├── event_scoring/                 # [TODO] Оценка значимости событий
│   │   └── agent.py
│   ├── consensus/                     # [TODO] Консенсус между несколькими агентами
│   │   └── agent.py
│   └── financial_analysis/            # [TODO] Комплексный финансовый анализ
│       └── ...
│
├── config.py                          # Загрузка конфигурации (env → YAML → defaults)
└── tests/
    ├── conftest.py                    # Фикстуры (reset singleton между тестами)
    └── test_core.py                   # Тесты ядра (~20 тестов)
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
                    через конструктор ↓
                                │
                          LLMAdapter, InMemoryCache, PromptManager
```

Агент не знает о конкретном провайдере — работает через протоколы.
Это позволяет подменять LLM на mock в тестах без изменения кода агента.

---

### Поток выполнения агента

```text
execute(context)
  │
  ├── _setup(context)                  # hook: подготовка
  │
  ├── _execute_internal(context)       # abstract: бизнес-логика наследника
  │     ├── _get_prompt(context)       #   PromptManager → (prompt, version)
  │     ├── _call_llm(prompt)          #   LLMAdapter → raw response
  │     └── _parse_response(raw)       #   JSON extraction + validation
  │
  ├── _handle_error(exception)         # при ошибке: graceful degradation
  │
  ├── _cleanup(context)                # hook: очистка ресурсов
  │
  └── return AgentResult               # frozen dataclass с метриками
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
  ├── retry logic (tenacity: exponential backoff)
  └── engine dispatch
        │
        ▼
  BaseLLMEngine (abstract)
    ├── OpenAICompatibleEngine        # sync + async + stream
    │     ├── OpenAIEngine            # GPT-4, GPT-4o
    │     ├── ClaudeEngine            # Anthropic (через совместимый API)
    │     └── GeminiEngine            # Google (через совместимый API)
    └── [Mock — встроен в LLMAdapter] # для тестов, без внешних вызовов
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

Retry срабатывает **только** на `LLMTransientError` и его потомков.

---

### Создание и валидация агентов

```text
AgentFactory                          AgentRegistry
  │ хранит: type → Class               │ хранит: type → Metadata
  │                                     │   (name, version, inputs,
  │                                     │    outputs, providers)
  ▼                                     ▼
factory.create_agent(type, config)    registry.get(type) → AgentMetadata
         │                                     │
         │              AgentValidator          │
         └──────────▶  validate(type, config) ◀─┘
                         │
                         ▼
                    ValidationResult
                      ├── is_valid: bool
                      └── errors: [ValidationError]
```

---

## Конфигурация

Приоритет загрузки: **ENV vars → YAML файл → defaults в коде**

| Переменная        | Описание                                                               | Default |
| ----------------- | ---------------------------------------------------------------------- | ------- |
| `LLM_PROVIDER`    | openai / claude / gemini / mock                                        | mock    |
| `LLM_MODEL`       | Название модели                                                        | gpt-4   |
| `LLM_TEMPERATURE` | Креативность (0.0–2.0)                                                 | 0.7     |
| `LLM_MAX_TOKENS`  | Макс. токенов ответа                                                   | 1000    |
| `API_KEY`         | API ключ (fallback: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY) | —       |
| `API_BASE_URL`    | Кастомный endpoint                                                     | —       |
| `API_RETRIES`     | Количество повторов                                                    | 3       |

---

## Статус реализации

| Компонент                             | Статус | Приоритет |
| ------------------------------------- | :----: | :-------: |
| BaseAgent + execute (sync/async)      |    ✅   |     —     |
| AgentFactory (thread-safe, создаётся через Container) |    ✅   |     —     |
| AgentRegistry (metadata, YAML)        |    ✅   |     —     |
| AgentValidator                        |    ✅   |     —     |
| LLMAdapter + retry + cache            |    ✅   |     —     |
| OpenAI-compatible engines             |    ✅   |     —     |
| Exception hierarchy                   |    ✅   |     —     |
| InMemoryCache (LRU)                   |    ✅   |     —     |
| Config loading (env + YAML)           |    ✅   |     —     |
| Tests (core, ~20)                     |    ✅   |     —     |
| PromptManager                         |    ⬜   |     P0    |
| Anonymizer / De-anonymizer            |    ⬜   |     P0    |
| User profile (aggressiveness)         |    ⬜   |     P1    |
| Task agents (event gen, scoring)      |    ⬜   |     P1    |
| Orchestrator                          |    ⬜   |     P1    |
| Tools (calculation, DB, ETL)          |    ⬜   |     P2    |
| Skills (file storage, JSON schema)    |    ⬜   |     P2    |
| Async retry в LLMAdapter              |    ⬜   |     P2    |
| UI / API layer                        |    ⬜   |     P3    |

---

## Планируемое расширение

```text
Текущее состояние                    Целевое состояние
─────────────────                    ─────────────────
agents/core/  ← framework           agents/core/        ← framework (стабильное)
agents/tasks/ ← пустые заглушки     agents/tasks/       ← 5-10 специализированных агентов
                                     agents/orchestrator/ ← маршрутизация + стратегия
                                     agents/anonymizer/   ← обезличивание данных
                                     agents/profiles/     ← профили агрессивности
                                     agents/api/          ← REST/WebSocket интерфейс
```
