from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys # Важный импорт для специальных клавиш
from selenium.webdriver.support import expected_conditions as EC
import re
from datetime import datetime, timedelta, time

from lib.browser import create_chrome_driver
from lib.comon_api import fetch_strategy_profit, profit_api_to_db_series
from lib.rate_limit import (
    pause_selenium_calc,
    pause_selenium_day,
    pause_selenium_page,
    pause_selenium_retry,
)
from lib.save import save_history_record_to_db
from lib.strategy import StrategyInfo
from lib.urlutils import extract_date_text, find_start_date_element
from lib.utils import extract_percentage
from models.strategies import History
from sqlalchemy import func

pattern = r"(?:https?:\/\/)?(?:www\.)?comon\.ru\/strategies\/\d+\/"


def extract_strategy_links(driver):
    links = []
    for a_tag in driver.find_elements(By.TAG_NAME, "a"):
        link_text = a_tag.get_attribute("href")
        if re.match(pattern, link_text) is None:
            continue
        ls = a_tag.text.split("\n")
        match = re.search(r'/(\d+)/?$', link_text)
        if not match:
            print("Номер не найден: ", link_text)
            continue
        number = match.group(1)
        info = StrategyInfo(ls, link_text)
        if not info.is_succes:
            print(link_text, "кривая", ls)
            continue
        links.append((link_text, info, number))
    return links


def get_links_selenium(url, driver=None):
    """
    Получает ссылки на стратегии со страницы comon.ru с помощью Selenium.

    Args:
        url: URL веб-страницы.
        driver: Опционально — уже открытый WebDriver для обхода нескольких страниц.

    Returns:
        Кортеж (список ссылок, число страниц) или ([], None) при ошибке.
    """
    try:
        if driver is None:
            driver = create_chrome_driver()

        driver.get(url)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "a"))
            )
        except Exception:
            print("Превышено время ожидания загрузки элементов.")
            return [], None

        driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
        pause_selenium_page()

        pages_count = get_pages_count(driver)
        links = extract_strategy_links(driver)
        return links, pages_count

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return [], None


def get_pages_count(driver):
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
    pause_selenium_page(scale=0.5)

    max_number = 0

    pagination_divs = driver.find_elements(By.CSS_SELECTOR, 'div[data-marker^="pagination-item"]')
    for div in pagination_divs:
        pag_text = div.get_attribute('data-marker')
        items = pag_text.split("/")
        number = items[-1]
        if number.isdigit():
            max_number = max(max_number, int(number))

    paginator_buttons = driver.find_elements(
        By.CSS_SELECTOR,
        'nav[class*="strategiesPagination"] button',
    )
    for button in paginator_buttons:
        text = button.text.strip()
        if text.isdigit():
            max_number = max(max_number, int(text))

    return max_number if max_number > 0 else 1

def set_date(div,driver,xpath,dt):
    items = div.find_elements(By.XPATH, xpath)
    formatted_date = dt.strftime("%d.%m.%Y")
    for item in items:
        driver.execute_script("arguments[0].setAttribute('value', arguments[1]);", item, formatted_date)

# Вместо вашей функции set_date
def set_date_keys(driver, xpath, dt): # Убрал 'div' из параметров, так как find_elements лучше делать от driver
    # Если xpath ведет к одному элементу, можно использовать find_element
    # Если к нескольким, тогда цикл по items
    items = driver.find_elements(By.XPATH, xpath)
    formatted_date = dt.strftime("%d.%m.%Y")
    for item in items:
        # 1. Очищаем поле
        #item.clear()
        # 2. Вводим новое значение
        item.send_keys(formatted_date)
        # 3. Вызываем событие blur
        driver.execute_script("arguments[0].blur();", item)
    print(f"Установлена дата: {formatted_date}")

def set_date_with_js_events(driver, xpath_locator, new_date):
    """
    Устанавливает дату в поле ввода, используя JavaScript,
    устанавливая свойство value и вызывая события input, change и blur.
    """
    formatted_date = new_date.strftime("%d.%m.%Y")

    date_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, xpath_locator))
    )

    # Скрипт для установки значения и вызова событий
    script = """
    var ele = arguments[0];
    var val = arguments[1];
    ele.value = val;
    // Создаем и вызываем события, чтобы веб-приложение "увидело" изменение
    ele.dispatchEvent(new Event('input', { bubbles: true }));
    ele.dispatchEvent(new Event('change', { bubbles: true }));
    ele.dispatchEvent(new Event('blur', { bubbles: true })); // Очень важно!
    """

    driver.execute_script(script, date_input, formatted_date)
    print(f"Установлена дата через JS-события: {formatted_date}")

def get_gate(driver, xpath_locator):
    date_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, xpath_locator))
    )
    date_str=date_input.get_attribute("value")
    date_format = "%d.%m.%Y"
    try:
        date_object = datetime.strptime(date_str, date_format)
        return date_object
    except ValueError:
        print("Неправильный формат даты")
        return None

def set_date_with_tab(driver, xpath_locator, new_date):
    """
    Устанавливает дату в поле ввода, используя send_keys() для ввода
    и Keys.TAB для потери фокуса, что должно вызвать необходимые JS-события.
    """
    formatted_date = new_date.strftime("%d.%m.%Y")
    #formatted_date = new_date.strftime("%d%m%Y")

    # Дожидаемся, пока элемент будет видим и кликабелен
    date_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, xpath_locator))
    )

    # 1. Очищаем поле, чтобы убедиться, что старое значение полностью удалено
    #date_input.clear()

    # 2. Вводим новое значение. Это также ставит фокус на поле.
    #date_input.send_keys(formatted_date)
    #date_input.send_keys(Keys.HOME)
    date_input.send_keys(Keys.END)
    for i in range(8):
        date_input.send_keys(Keys.BACKSPACE)
    date_input.send_keys(formatted_date)

    #driver.execute_script("arguments[0].setAttribute('value', arguments[1]);", date_input, formatted_date)

    # 3. Самое главное: имитируем нажатие клавиши TAB
    # Это вызовет событие blur, которое, по вашим наблюдениям, приводит к фиксации даты.
    date_input.send_keys(Keys.TAB)

    # Опционально: Можно добавить небольшую паузу, если приложение требует времени
    # на обработку события TAB и обновление своего внутреннего состояния.
    # time.sleep(0.5)

    print(f"Установлена дата с помощью send_keys + TAB: {formatted_date}")

def set_date_with_check(driver, x_locator, new_date):
    date_time=get_gate(driver, x_locator)
    print("До установки",date_time)
    set_date_with_tab(driver, x_locator,new_date)
    date_time = get_gate(driver, x_locator)
    print("После установки", date_time)
    if date_time!=new_date:
        raise Exception("Не получилось установить дату")

def set_period(driver, beg_set_date, end_set_date, x_locator_beg, x_locator_end):
    #beg_date=get_gate(driver, x_locator_beg)
    end_date = get_gate(driver, x_locator_end)
    if beg_set_date>=end_date:
        set_date_with_check(driver,x_locator_end, end_set_date)
        set_date_with_check(driver, x_locator_beg, beg_set_date)
    else:
        set_date_with_check(driver, x_locator_beg, beg_set_date)
        set_date_with_check(driver,x_locator_end, end_set_date)

def get_summ_perc(driver,last_perc):
    button_locator_x='//*[@id="profit-calc-btn"]'
    items = driver.find_elements(By.XPATH, button_locator_x) #id=profit-calc-btn
    perc=None
    text=None
    count=4
    i=0
    retry_scale=1.0
    while i<count:
        for button_locator in items:
            try:
                # Ждем до 10 секунд, пока элемент не станет кликабельным
                button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(button_locator)
                )
                button.click()
            except Exception as ex:
                print("Не смогли кликнуть:",i,count,ex)
                count+=2
                retry_scale*=1.1
                continue
            finally:
                pause_selenium_calc(scale=retry_scale)
        items = driver.find_elements(By.ID, 'profit-calc-parameter-header-profit')
        for item in items:
            counter=1
            success = False
            while not success:
                success=True
                try:
                    perc = extract_percentage(item.text)
                except Exception as ex:
                    if counter>5:
                        raise Exception(ex)
                    success=False
                    counter+=1
                    pause_selenium_retry(scale=retry_scale)
            text=item.text
            if True or perc != last_perc or perc > 0.01:
                return perc,text.replace("₽", 'руб.')
        i+=1
        #raise Exception("Что-то не смогли взять сумму")
    return perc,text.replace("₽", 'руб.')


def load_strategy_history_from_api(
    strategy_number,
    session,
    strategy_id,
    end_date_today,
    from_date=None,
    replace=False,
):
    """
    Загрузка истории через GET /api/v1/strategies/{number}/profit.
    Границы периода совпадают с Selenium-режимом load_strategy_history.
    При ошибке API/данных — исключение (для fallback).
    Если грузить нечего — None.
    """
    end_date_today = datetime.combine(end_date_today.date(), time.min)

    next_date = None
    if from_date is not None:
        begin_date = datetime.combine(
            from_date.date() if isinstance(from_date, datetime) else from_date,
            time.min,
        )
        end_exclusive = end_date_today + timedelta(days=1)
        if begin_date >= end_exclusive:
            print(
                f'Пропуск: начало периода {begin_date:%d.%m.%Y} не раньше конца '
                f'{end_date_today:%d.%m.%Y}',
            )
            return None
        mode_label = 'Перезагрузка' if replace else 'Загрузка'
        print(
            f'{mode_label} (API) strategy_id={strategy_id} за период '
            f'{begin_date:%d.%m.%Y} — {end_date_today:%d.%m.%Y}',
        )
    else:
        last_in_db = session.query(func.max(History.datetime)).filter(
            History.strategy_id == strategy_id,
        ).scalar()
        if last_in_db is None:
            next_date = datetime(1970, 1, 1)
        else:
            next_date = datetime.combine(last_in_db + timedelta(days=1), time.min)
        if next_date + timedelta(days=1) >= end_date_today:
            if last_in_db is None:
                print('Пропуск: нечего загружать до', end_date_today.strftime('%d.%m.%Y'))
            else:
                print(
                    f'История актуальна: последняя запись в БД {last_in_db:%d.%m.%Y}, '
                    f'конечная дата загрузки {end_date_today:%d.%m.%Y}',
                )
            return None
        print(f'Загрузка (API) с {next_date:%d.%m.%Y} для strategy_id={strategy_id}')
        end_exclusive = end_date_today

    points = fetch_strategy_profit(strategy_number)
    series = profit_api_to_db_series(points)
    if not series:
        raise ValueError(f'API вернул пустую историю для №{strategy_number}')

    strategy_start = datetime.combine(min(series.keys()), time.min)

    if from_date is not None:
        end_exclusive = end_date_today + timedelta(days=1)
        if begin_date < strategy_start:
            print(
                f'Начало периода скорректировано: {begin_date:%d.%m.%Y} -> '
                f'{strategy_start:%d.%m.%Y} (дата старта по API)',
            )
            begin_date = strategy_start
        if begin_date >= end_exclusive:
            print('Пропуск: после корректировки период пуст')
            return None
        last_inclusive = end_date_today.date()
    else:
        begin_date = strategy_start
        if next_date > begin_date:
            begin_date = next_date
        if begin_date >= end_exclusive:
            print('Пропуск: после корректировки период пуст')
            return None
        last_inclusive = (end_exclusive - timedelta(days=1)).date()

    days_to_load = [
        day for day in sorted(series)
        if begin_date.date() <= day <= last_inclusive
    ]
    if not days_to_load:
        print('Пропуск: в API нет точек за выбранный период')
        return None

    for day in days_to_load:
        perc = round(series[day], 6)
        perc_text = f'{perc:.6f} %'
        save_history_record_to_db(
            strategy_id,
            day,
            perc,
            perc_text,
            replace=replace,
            session=session,
        )

    loaded_begin = datetime.combine(days_to_load[0], time.min)
    loaded_end = datetime.combine(days_to_load[-1], time.min)
    print(
        f'API: записано дней={len(days_to_load)} '
        f'({loaded_begin:%d.%m.%Y} — {loaded_end:%d.%m.%Y})',
    )
    return loaded_begin, loaded_end


def load_strategy_history_auto(
    driver,
    url,
    session,
    strategy_id,
    end_date_today,
    strategy_number,
    from_date=None,
    replace=False,
    use_api=False,
):
    """
    При use_api=True пробует API; при ошибке — Selenium (load_strategy_history).
    Проверка после загрузки остаётся снаружи (verify_strategy_history).
    """
    if use_api:
        try:
            return load_strategy_history_from_api(
                strategy_number,
                session,
                strategy_id,
                end_date_today,
                from_date=from_date,
                replace=replace,
            )
        except Exception as exc:
            print(
                f'API загрузка для №{strategy_number} не удалась ({exc}). '
                f'Fallback на Selenium.',
            )

    return load_strategy_history(
        driver,
        url,
        session,
        strategy_id,
        end_date_today,
        from_date=from_date,
        replace=replace,
    )


def load_strategy_history(
    driver,
    url,
    session,
    strategy_id,
    end_date_today,
    from_date=None,
    replace=False,
):
    end_date_today = datetime.combine(end_date_today.date(), time.min)

    if from_date is not None:
        begin_date = datetime.combine(from_date.date(), time.min) if isinstance(from_date, datetime) else datetime.combine(from_date, time.min)
        # Верхняя граница цикла — exclusive, поэтому +1 день к включительной end-date
        end_date = end_date_today + timedelta(days=1)
        if begin_date >= end_date:
            print(
                f'Пропуск: начало периода {begin_date:%d.%m.%Y} не раньше конца {end_date_today:%d.%m.%Y}',
            )
            return None
        mode_label = 'Перезагрузка' if replace else 'Загрузка'
        print(
            f'{mode_label} strategy_id={strategy_id} за период '
            f'{begin_date:%d.%m.%Y} — {end_date_today:%d.%m.%Y}',
        )
    else:
        last_in_db = session.query(func.max(History.datetime)).filter(
            History.strategy_id == strategy_id,
        ).scalar()
        if last_in_db is None:
            next_date = datetime(1970, 1, 1)
        else:
            next_date = datetime.combine(last_in_db + timedelta(days=1), time.min)
        if next_date + timedelta(days=1) >= end_date_today:
            if last_in_db is None:
                print('Пропуск: нечего загружать до', end_date_today.strftime('%d.%m.%Y'))
            else:
                print(
                    f'История актуальна: последняя запись в БД {last_in_db:%d.%m.%Y}, '
                    f'конечная дата загрузки {end_date_today:%d.%m.%Y}',
                )
            return None

        print(f"Загрузка с {next_date:%d.%m.%Y} для strategy_id={strategy_id}")
        begin_date = None
        end_date = datetime.now()
        if end_date > end_date_today:
            end_date = end_date_today

    x_locator_beg = '//*[@id="profit-calc-date-from-input"]'
    x_locator_end = '//*[@id="profit-calc-date-to-input"]'

    # Переход по указанному URL
    driver.get(url)
    pause_selenium_page()

    date_info = find_start_date_element(driver)
    if date_info is None:
        print('Пропуск: не удалось найти дату старта стратегии на странице', url)
        return None
    date_str = extract_date_text(date_info)
    if date_str is None:
        print('Пропуск: не удалось прочитать дату старта стратегии на странице', url)
        return None
    date_format = "%d.%m.%Y"
    try:
        date_object = datetime.strptime(date_str, date_format)
    except ValueError:
        print("Неправильный формат даты")
        exit(1)

    if from_date is not None:
        if begin_date < date_object:
            print(
                f'Начало периода скорректировано: {begin_date:%d.%m.%Y} → {date_object:%d.%m.%Y} '
                f'(дата старта стратегии)',
            )
            begin_date = date_object
        if begin_date >= end_date:
            print('Пропуск: после корректировки период пуст')
            return None
    else:
        begin_date = date_object
        if next_date > begin_date:
            begin_date = next_date

    last_summ = None
    beg_set_date = begin_date
    while True:
        end_set_date = beg_set_date + timedelta(days=1)
        if end_set_date >= end_date:
            break
        set_period(driver, beg_set_date, end_set_date, x_locator_beg, x_locator_end)
        perc, perc_text = get_summ_perc(driver, last_summ)
        save_history_record_to_db(
            strategy_id, beg_set_date, perc, perc_text, replace=replace, session=session,
        )
        last_summ = perc
        beg_set_date = end_set_date
        pause_selenium_day()

    loaded_period_end = beg_set_date - timedelta(days=1)
    if loaded_period_end < begin_date:
        return None
    return begin_date, loaded_period_end