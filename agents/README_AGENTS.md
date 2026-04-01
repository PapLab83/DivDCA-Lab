# DivDCA-Lab / Agents

## Что это

Мультиагентная система — ядро AI-консультанта по долгосрочным инвестициям в акции.

Система строится вокруг нескольких ключевых идей:

* **Обезличивание данных.** LLM не получает реальные тикеры и названия компаний.
  Вместо "AAPL" модель видит "STOCK_0042". Это исключает ситуацию, когда модель
  «вспоминает» из обучающих данных, что конкретная акция вырастет в конкретный период,
  и заставляет опираться исключительно на числовые паттерны — дивидендную доходность,
  волатильность, финансовые метрики.

* **Адаптивный профиль риска.** Обычный пользователь получает консервативные
  рекомендации (высокая дивидендная доходность, низкая волатильность, длинный горизонт).
  Продвинутый пользователь может сдвигать параметры агрессивности: снижать пороги
  доходности, допускать growth-акции, сокращать горизонт удержания.

* **Мультиагентная архитектура.** Каждая задача (генерация событий, скоринг,
  консенсус, финансовый анализ) выполняется отдельным агентом. Агенты независимы,
  переиспользуют общее ядро и могут комбинироваться оркестратором в цепочки.

* **Провайдер-агностичность.** Единый интерфейс к OpenAI, Claude, Gemini.
  Смена провайдера — одна переменная окружения. Mock-режим для разработки без API-ключей.

> **Статус:** прототип. Ядро (core) готово, task-агенты в разработке.

---

## Быстрый старт

### Установка

```bash
git clone <repo_url>
cd DivDCA-Lab
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Конфигурация

```bash
# .env или export
LLM_PROVIDER=mock              # openai | claude | gemini | mock
LLM_MODEL=gpt-4
API_KEY=sk-...                 # или OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=1000
```

Приоритет: ENV → YAML (`config.yaml`) → defaults в коде.

### Запуск тестов

```bash
pytest agents/tests/ -v
```

---

## Использование (API — в разработке)

```python
from agents.config import load_agent_config
from agents.core.agent_factory import AgentFactory
from agents.core.base_agent import AgentContext
from agents.core.llm.adapter import LLMAdapter

# Конфигурация
config = load_agent_config(provider="mock")
adapter = LLMAdapter(config.llm_config, config.api_config)

# Создание агента
factory = AgentFactory()
factory.register("event_generation", EventGenerationAgent)
agent = factory.create_agent("event_generation", config, llm_adapter=adapter)

# Выполнение
context = AgentContext(agent_id="run-001", task="event_generation")
result = agent.execute(context)

print(result.success)       # True
print(result.data)          # {"reason_short": "...", "confidence": 0.85}
print(result.duration_ms)   # 1200
```

---

## Структура проекта

```text
agents/
├── core/                          # Ядро — не зависит от конкретных задач
│   ├── base_agent.py              # BaseAgent, Protocol'ы, Config, Result
│   ├── agent_factory.py           # Фабрика (singleton, thread-safe)
│   ├── agent_registry.py          # Реестр метаданных агентов
│   ├── agent_validator.py         # Валидация агент ↔ конфиг
│   ├── prompt_manager.py          # [TODO] Шаблоны промптов
│   ├── llm/                       # LLM-слой
│   │   ├── adapter.py             # Единый интерфейс + cache + retry
│   │   ├── exceptions.py          # Иерархия ошибок
│   │   └── engines/               # OpenAI, Claude, Gemini
│   ├── skills/                    # Внутренние способности (cache, валидация, хранение)
│   └── tools/                     # Внешние инструменты (БД, расчёты, ETL)
├── tasks/                         # [TODO] Конкретные агенты-задачи
│   ├── event_generation/
│   ├── event_scoring/
│   ├── consensus/
│   └── financial_analysis/
├── config.py                      # Загрузка конфигурации
└── tests/                         # Тесты ядра
```

> Подробнее об архитектуре, потоках данных и паттернах — см. `ARCHITECTURE.md`

---

## Skills vs Tools

|             | **Skills**                          | **Tools**                             |
| ----------- | ----------------------------------- | ------------------------------------- |
| Суть        | Внутренние способности агента       | Внешние инструменты                   |
| Зависимости | Нет (in-process)                    | БД, API, файлы                        |
| Примеры     | Кэш, JSON-валидация, форматирование | Расчёт DCF, запрос к БД, загрузка CSV |
| Аналогия    | Память, грамотность                 | Калькулятор, справочник               |

---

## Переменные окружения

| Переменная        | Описание               | Default |
| ----------------- | ---------------------- | ------- |
| `LLM_PROVIDER`    | Провайдер LLM          | `mock`  |
| `LLM_MODEL`       | Модель                 | `gpt-4` |
| `LLM_TEMPERATURE` | Креативность (0.0–2.0) | `0.7`   |
| `LLM_MAX_TOKENS`  | Лимит токенов ответа   | `1000`  |
| `API_KEY`         | API-ключ               | —       |
| `API_BASE_URL`    | Кастомный endpoint     | —       |
| `API_RETRIES`     | Повторы при ошибках    | `3`     |
| `API_TIMEOUT`     | Таймаут (сек)          | `30`    |

---

## Статус

| Компонент                                                | Готовность |
| -------------------------------------------------------- | :--------: |
| Core framework (BaseAgent, Factory, Registry, Validator) |      ✅     |
| LLM layer (Adapter, Engines, Exceptions, Cache)          |      ✅     |
| Config (env + YAML)                                      |      ✅     |
| Тесты ядра                                               |      ✅     |
| PromptManager                                            |      ⬜     |
| Anonymizer / De-anonymizer                               |      ⬜     |
| Task-агенты                                              |      ⬜     |
| Профили агрессивности                                    |      ⬜     |
| Orchestrator                                             |      ⬜     |
| REST API                                                 |      ⬜     |

---

