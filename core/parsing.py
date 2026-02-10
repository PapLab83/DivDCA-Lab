import yfinance as yf
import pandas as pd

COMPANY_NAMES = {
    'JNJ': 'Johnson & Johnson',
    'PG': 'Procter & Gamble',
    'KO': 'Coca-Cola',
    'MCD': 'McDonald\'s',
    'O': 'Realty Income',
    'JPM': 'JPMorgan Chase',
    'BAC': 'Bank of America',
    'BLK': 'BlackRock',
    'AVGO': 'Broadcom Inc.',
    'TXN': 'Texas Instruments',
    'XOM': 'Exxon Mobil',
    'CVX': 'Chevron',
    'MMM': '3M Company',
    'ABBV': 'AbbVie',
    'AMT': 'American Tower',
    'CCI': 'Crown Castle',
    'MSFT': 'Microsoft',
    'AAPL': 'Apple',
    'LOW': 'Lowe\'s',
    'HD': 'Home Depot',
    'PM': 'Philip Morris',
    'MO': 'Altria Group',
    'KHC': 'Kraft Heinz',
    'PEP': 'PepsiCo',
    'WMT': 'Walmart',
    'TGT': 'Target',
    'NEE': 'NextEra Energy',
    'SO': 'Southern Company',
    'DUK': 'Duke Energy',
    'IBM': 'International Business Machines',
    'VZ': 'Verizon'
}
COMPANY = "JPM"

# Получаем данные
ticker = yf.Ticker(COMPANY)

# Получаем исторические данные
hist = ticker.history(start="1985-01-01", end="2025-12-31")

print("Колонки:")
print(hist.columns.tolist())

# Фильтруем по концам годов
year_end = hist.resample('YE').last()

# Берем цену закрытия
result = year_end[['Close']].copy()

# Получаем дивиденды
divs = ticker.dividends
annual_divs = divs.resample('YE').sum()

# Получаем сплиты
splits = ticker.splits
annual_splits = splits.resample('YE').last()

# Объединяем все
result['div_annual'] = annual_divs
result['stock_splits'] = annual_splits

# Форматируем даты и сбрасываем индекс
result.index = result.index.strftime('%Y-%m-%d')
result = result.reset_index()

# Заменяем NaN на пустые строки или 0 для лучшего отображения
result['stock_splits'] = result['stock_splits'].fillna(1.0)  # 1.0 = нет сплита

print("\nИтоговые данные (цена + дивиденды + сплиты):")
print(result.to_string(index=False, na_rep='-'))

# Отдельно выводим только годы со сплитами (для наглядности)
print("\n" + "=" * 60)
print(f"Годы со сплитами акций {COMPANY}:")
splits_years = result[result['stock_splits'] != 1.0]
if not splits_years.empty:
    for _, row in splits_years.iterrows():
        split_value = row['stock_splits']
        # Конвертируем в человеко-читаемый формат
        if split_value > 1:
            # Например, 2.0 -> "2-for-1"
            ratio = f"{int(split_value)}-for-1"
        elif split_value < 1:
            # Обратный сплит, например 0.5 -> "1-for-2"
            ratio = f"1-for-{int(1 / split_value)}"
        else:
            ratio = "No split"

        print(f"{row['Date']}: Split {ratio} (Value: {split_value})")
else:
    print("Сплитов не найдено в выбранном периоде.")

# Дополнительная информация о сплитах
print("\n" + "=" * 60)
print(f"Полная история сплитов {COMPANY} (все доступные данные):")
all_splits = ticker.splits
if not all_splits.empty:
    for date, split_value in all_splits.items():
        date_str = date.strftime('%Y-%m-%d')
        if split_value > 1:
            ratio = f"{int(split_value)}-for-1"
        elif split_value < 1:
            ratio = f"1-for-{int(1 / split_value)}"
        else:
            ratio = "No split"
        print(f"{date_str}: {ratio}")
else:
    print("История сплитов не найдена.")

# Сохраняем в CSV для дальнейшего анализа
# result.to_csv(f'{COMPANY}_annual_data_with_splits.csv', index=False)
# print(f"\nДанные сохранены в файл: {COMPANY}_annual_data_with_splits.csv")