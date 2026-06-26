from sqlalchemy import create_engine, Column, Integer, String, Date, Numeric, ForeignKey, func
from selenium import webdriver

from lib.load import set_period, get_summ_perc
from models.strategies import History, Strategy
from lib.save import create_session

# Запрос на SQLAlchemy ORM
session=create_session()

query = session.query(
    History.strategy_id,
    func.min(History.datetime).label('min_datetime'), # label() для читабельности результата
    func.max(History.datetime).label('max_datetime'),
    Strategy.name,
    Strategy.link_text
).outerjoin(
    Strategy,
    History.strategy_id == Strategy.id # Указываем условие соединения
).group_by(
    History.strategy_id,
    Strategy.name,
    Strategy.link_text
).order_by(
    History.strategy_id
)

# Выполнение запроса и вывод результатов
results = query.all()

driver = webdriver.Chrome()
x_locator_beg = '//*[@id="profit-calc-date-from-input"]'
x_locator_end = '// *[ @ id = "profit-calc-date-to-input"]'

print("--- Результаты проверки ---")
for row in results:
    query_hist = session.query(History).filter(History.strategy_id == row.strategy_id)
    depo=1.0
    for hostory_row in query_hist.all():
        perc_income_day = hostory_row.perc_income_day
        depo = depo * (1.0 + float(perc_income_day) / 100.0)
    driver.get(row.link_text)
    set_period(driver, row.min_datetime, row.max_datetime, x_locator_beg, x_locator_end)
    perc, perc_text = get_summ_perc(driver, None)
    depo_real=1.0+perc/100.0
    print(row.name,depo,depo_real) отглючить
    #print(f"Strategy ID: {row.strategy_id}, Min Date: {row.min_datetime}, Max Date: {row.max_datetime}, Name: {row.name}, Link: {row.link_text}")
