# DivDCA-Lab

Инструмент для анализа стратегии DCA (Dollar Cost Averaging) на дивидендных акциях. Симулирует портфель на исторических данных и считает ключевые метрики: ROI, CAGR, доходность на себестоимость, накопленные дивиденды.

---

## Быстрый старт

### 1. ETL — подготовка данных

**Загрузка сырых данных из Yahoo Finance:**
```bash
python scripts/extract.py --ticker JPM --start 2000-01-01 --end 2025-12-31
```
Результат: `data/extracted/prices_JPM.jsonl`, `dividends_JPM.jsonl`, `splits_JPM.jsonl`

**Трансформация в расчётный формат:**
```bash
python scripts/transform.py --ticker JPM
```
Результат: `data/transformed/JPM.jsonl` — годовые записи с ценой, дивидендами и комментариями.

> Файл `reasons_JPM.jsonl` (комментарии к годам) добавляется вручную или через GPT-агента.

### 2. Расчёт и отчёт

```python
from calculations.orchestrator import create_orchestrator

orchestrator = create_orchestrator(ticker="JPM", start_year=2000, end_year=2025, annual_investment=12000)
orchestrator.run()
```
Результат: Excel-отчёт в `data/reported/tables/`

---

## Архитектура

```
DivDCA-Lab/
├── config/           # Параметры стратегии (тикер, период, сумма инвестиций)
├── etl/
│   ├── fetch/        # Загрузка данных (Yahoo Finance, провайдеры)
│   └── transform/    # Сборка годового датасета (цены + дивиденды + сплиты + reasons)
├── calculations/
│   ├── data_provider.py      # Чтение JSONL для расчётов
│   ├── data_validator.py     # Валидация данных
│   ├── portfolio_simulator.py # Ядро: симуляция DCA
│   ├── table_exporter.py     # Экспорт в Excel/CSV
│   └── orchestrator.py       # Координатор всего пайплайна
├── scripts/          # CLI точки входа (extract.py, transform.py)
├── data/
│   ├── extracted/    # Сырые данные от провайдеров
│   ├── transformed/  # Готовые данные для расчётов
│   └── reported/     # Финальные отчёты
└── tests/            # (пусто — см. техдолг)
```

**Поток данных:**
```
Yahoo Finance → extract → transform → calculations → Excel-отчёт
```

---

## Формат входных данных

`data/filtered/TICKER.jsonl` — одна строка на год:
```json
{"date": "2023-12-31", "price": 150.0, "div_annual": 4.52, "reason_short": "Рост прибыли", "reason_long": "..."}
```

---

## Текущие ограничения

- Реализована только стратегия **с реинвестированием дивидендов**
- Только **годовая** гранулярность данных
- Один тикер за один запуск

---

## Технический долг

- Дублирование `COMPANY_NAMES` в двух местах
- Синглтоны с накапливаемым состоянием (валидатор)
- Валидатор жёстко привязан к глобальному конфигу
- Нет тестов

## Известные баги

- Баг потери данных в `format_final_report` (дублирующийся ключ в `column_mapping`)
- Двойной вызов API в `run_fetcher` (`fetch()` вызывается дважды)
- Ширина колонок Excel сломается при >26 колонках

---

## Roadmap

| Направление | Что нужно |
|---|---|
| **AI-агенты** | Сбор новостей, анализ финпоказателей, рекомендации по тикерам |
| **База данных** | Хранение исторических данных и результатов расчётов |
| **Веб-интерфейс** | Запуск анализа, просмотр отчётов в браузере |
| **Докеризация** | Упаковка приложения и зависимостей |
| **Удалённый сервер** | Деплой и фоновый запуск агентов |