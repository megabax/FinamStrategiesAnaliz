from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta, time

from selenium.webdriver.support.wait import WebDriverWait
from sqlalchemy import func

from lib.load import set_date, set_date_with_js_events, set_date_keys, set_date_with_tab, get_gate, set_date_with_check, \
    set_period, get_summ_perc, load_strategy_history
from lib.save import save_history_record_to_db, create_session
from lib.utils import extract_percentage
from models.strategies import History, Strategy

end_date=datetime(2025,11,26)

#strategy_id=2
#print(f"Максимальное значение datetime для strategy_id=1: {max_datetime_from_db}")

#url="https://www.comon.ru/strategies/115412/"

надо сделать тест
# Создание экземпляра веб-драйвера Chrome.  Не используем Options, чтобы видеть браузер.
driver = webdriver.Chrome()

# Запрос на SQLAlchemy ORM
session=create_session()
query=session.query(Strategy)
start_date=datetime.now()
for strategy_row in query.all():
    strategy_id=strategy_row.id
    url=strategy_row.link_text
    #print(f"ID: {strategy_row.id}, Имя: {strategy_row.name}, Подписчики: {strategy_row.subscribers}, Тип: {strategy_row.kind.name}")
    if not load_strategy_history(driver, url, session, strategy_id, end_date):
        print("Пропустили стратегию",strategy_id)
    print("Прошло времени",datetime.now()-start_date)

# all_strategies = session.query(Strategy).all()
# for strategy in all_strategies:
#     print(f"  ID: {strategy.id}, Номер: {strategy.number}, Название: {strategy.name}, "
#           f"Тип: {strategy.kind.name}, Подписчики: {strategy.subscribers}, "
#           f"Ссылка: {strategy.link_text}")
#
# print("-" * 30)
# exit(1)







