import yfinance as yf
import pandas as pd

# Самый простой способ
ticker = yf.Ticker("JNJ")

# Получаем исторические данные
hist = ticker.history(start="1970-01-01", end="2025-12-31")

print("Колонки:")
print(hist.columns.tolist())

# Фильтруем по концам годов
year_end = hist.resample('YE').last()

# Берем только скорректированную цену
result = year_end[['Close']].copy()  # или 'Close' если хотите обычную цену

# Получаем дивиденды
divs = ticker.dividends
annual_divs = divs.resample('YE').sum()

# Объединяем
result['div_annual'] = annual_divs
result.index = result.index.strftime('%Y-%m-%d')
result = result.reset_index()

print("\nИтоговые данные:")
print(result.to_string(index=False))