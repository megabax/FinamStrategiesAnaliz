import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import select
from lib.save import create_session
from models.strategies import History

strategy_id = 1
window_size = 100 # Размер окна для скользящего среднего и среднеквадратичного отклонения

# --- Загрузка данных в DataFrame (используем pd.read_sql) ---
session = create_session()
stmt = select(History.datetime, History.perc_income_day).filter(History.strategy_id == strategy_id)
df = pd.read_sql(stmt, session.bind)
session.close() # Закрываем сессию после загрузки данных

# Убедимся, что столбец 'datetime' имеет правильный тип данных и установлен как индекс
df['datetime'] = pd.to_datetime(df['datetime'])
df.set_index('datetime', inplace=True)
# Сортируем по индексу, чтобы скользящие функции работали корректно
df.sort_index(inplace=True)

# --- Вычисление скользящего среднего и среднеквадратичного отклонения ---

# Скользящее среднее
df['moving_avg'] = df['perc_income_day'].rolling(window=window_size).mean()

# Скользящее среднеквадратичное отклонение
# Для среднеквадратичного отклонения часто используют .std()
df['moving_std'] = df['perc_income_day'].rolling(window=window_size).std()

# Вычисляем верхнюю и нижнюю границы зоны колебаний
df['upper_band'] = df['moving_avg'] + df['moving_std']
df['lower_band'] = df['moving_avg'] - df['moving_std']

# --- Визуализация ---

plt.figure(figsize=(14, 8)) # Размер графика

# График исходных данных
plt.plot(df.index, df['perc_income_day'], label='Процент дохода за день', color='skyblue', alpha=0.7)

# График скользящего среднего
plt.plot(df.index, df['moving_avg'], label=f'Скользящее среднее ({window_size} дней)', color='orange', linewidth=2)

# График верхней границы зоны колебаний
plt.plot(df.index, df['upper_band'], label='Верхняя зона колебаний (MA + STD)', color='red', linestyle='--', alpha=0.6)

# График нижней границы зоны колебаний
plt.plot(df.index, df['lower_band'], label='Нижняя зона колебаний (MA - STD)', color='green', linestyle='--', alpha=0.6)

# Заполнение зоны между верхним и нижним графиками
plt.fill_between(df.index, df['lower_band'], df['upper_band'], color='gray', alpha=0.2)

# Добавление заголовков и подписей
plt.title('Динамика процента дохода за день со скользящим средним и зоной колебаний')
plt.xlabel('Дата')
plt.ylabel('Процент дохода')
plt.legend() # Отображение легенды
plt.grid(True) # Отображение сетки

# Показываем график
plt.tight_layout() # Автоматическая корректировка параметров подграфика для плотного размещения
plt.show()

# Выведем последние несколько строк DataFrame с новыми колонками для проверки
print("\nDataFrame с рассчитанными показателями:")
print(df.tail())
