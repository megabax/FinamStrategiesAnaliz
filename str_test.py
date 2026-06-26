from lib.save import create_session
from models.strategies import History
import matplotlib.pyplot as plt
import numpy as np

strategy_id=1
avg=0.275333
std=2.10488518716218

session=create_session()
query=session.query(History).filter(History.strategy_id == strategy_id)
depo=1.0
dates = []      # Список для дат
depo_values = []
model_depo_values=[]
model_depo=1.0

for hostory_row in query.all():
    date_time=hostory_row.datetime
    perc_income_day=hostory_row.perc_income_day
    depo=depo*(1.0+float(perc_income_day)/100.0)
    print(date_time,perc_income_day,depo)

    # Добавляем данные в наши списки
    dates.append(date_time)
    depo_values.append(depo)

changes=np.random.normal(loc=avg, scale=std, size=len(depo_values))
for change in changes:
    model_depo = model_depo * (1.0 + float(change) / 100.0)
    model_depo_values.append(model_depo)


# --- Блок построения графика ---

if not dates: # Проверяем, есть ли данные для построения
    print("Нет данных для построения графика.")
else:
    plt.figure(figsize=(12, 6)) # Устанавливаем размер графика для лучшей читаемости
    plt.plot(dates, depo_values, linestyle='-', color='blue', label='Стоимость портфеля')
    plt.plot(dates, model_depo_values, linestyle='-', color='red', label='Стоимость модельного портфеля')

    # Добавляем подписи и заголовок
    plt.xlabel('Дата')
    plt.ylabel('Стоимость Портфеля')
    plt.title(f'Динамика Портфеля для Стратегии {strategy_id}')
    plt.grid(True) # Добавляем сетку
    plt.legend() # Отображаем легенду

    # Автоматически форматируем даты на оси X, чтобы они не накладывались друг на друга
    plt.gcf().autofmt_xdate()

    plt.tight_layout() # Корректирует расположение элементов, чтобы они не перекрывались
    plt.show() # Показываем график