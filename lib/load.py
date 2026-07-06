from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys # Важный импорт для специальных клавиш
from selenium.webdriver.support import expected_conditions as EC
import re
import time as tm
from sqlalchemy import func
from datetime import datetime, timedelta, time

from lib.save import save_history_record_to_db
from lib.strategy import StrategyInfo
from lib.urlutils import extract_date_text, find_start_date_element
from lib.utils import extract_percentage
from models.strategies import History

pattern = r"(?:https?:\/\/)?(?:www\.)?comon\.ru\/strategies\/\d+\/"

def get_links_selenium(url):
    """
    Получает HTML-контент по указанному URL с помощью Selenium и извлекает все ссылки (теги <a>).
    Открывает окно браузера, чтобы можно было видеть процесс.

    Args:
        url: URL веб-страницы.

    Returns:
        Список строк, представляющих собой URL-адреса, найденные на странице.
        Возвращает пустой список, если произошла ошибка или ссылки не найдены.
    """
    try:
        # Создание экземпляра веб-драйвера Chrome.  Не используем Options, чтобы видеть браузер.
        driver = webdriver.Chrome()

        # Переход по указанному URL
        driver.get(url)

        # Ожидание загрузки элементов на странице (например, ждем появления хотя бы одного тега <a>)
        try:
          WebDriverWait(driver, 10).until(
              EC.presence_of_element_located((By.TAG_NAME, "a"))
          )
        except:
          print("Превышено время ожидания загрузки элементов.")
          return [], None

        pages_count=get_pages_count(driver)

        # Поиск всех тегов <a> на странице
        a_tags = driver.find_elements(By.TAG_NAME, "a")
        links=[]
        for a_tag in a_tags:
            link_text=a_tag.get_attribute("href")
            if re.match(pattern, link_text) is not None:
                ls=a_tag.text.split("\n")
                match = re.search(r'/(\d+)/?$', link_text)
                if match:
                    number = match.group(1)  # Извлекаем захваченную группу (цифры)
                else:
                    print("Номер не найден: ",link_text)
                info=StrategyInfo(ls,link_text)
                if not(info.is_succes):
                    print(link_text,"кривая",ls)
                    continue
                links.append((link_text,info,number))

        return links, pages_count

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return [], None
    finally:
        # Закрытие веб-драйвера, чтобы освободить ресурсы
        #Раскомментируйте driver.quit() если не хотите чтобы окно оставалось открытым
        # try:
        #     driver.quit()
        # except:
        #     pass # Ignore errors during driver.quit()
        pass #Оставляем окно браузера открытым


def get_pages_count(driver):
    pagination_divs = driver.find_elements(By.CSS_SELECTOR, 'div[data-marker^="pagination-item"]')

    # Выводим атрибуты data-marker для проверки
    max_number=0
    for div in pagination_divs:
        pag_text=div.get_attribute('data-marker')
        items=pag_text.split("/")
        number=items[-1]
        if number.isdigit():
            num=int(number)
            if num>max_number:
                max_number=num

    return max_number

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
    delay=0.5
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
                delay*=1.1
                continue
            finally:
                tm.sleep(delay)
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
                    tm.sleep(2)
            text=item.text
            if True or perc != last_perc or perc > 0.01:
                return perc,text.replace("₽", 'руб.')
        i+=1
        #raise Exception("Что-то не смогли взять сумму")
    return perc,text.replace("₽", 'руб.')

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

    if replace:
        if from_date is None:
            raise ValueError('Для перезагрузки необходимо указать from_date')
        begin_date = datetime.combine(from_date.date(), time.min) if isinstance(from_date, datetime) else datetime.combine(from_date, time.min)
        # Верхняя граница цикла — exclusive, поэтому +1 день к включительной end-date
        end_date = end_date_today + timedelta(days=1)
        if begin_date >= end_date:
            print(
                f'Пропуск: начало периода {begin_date:%d.%m.%Y} не раньше конца {end_date_today:%d.%m.%Y}',
            )
            return False
        print(
            f'Перезагрузка strategy_id={strategy_id} за период '
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
            return False

        print(f"Загрузка с {next_date:%d.%m.%Y} для strategy_id={strategy_id}")
        begin_date = None
        end_date = datetime.now()
        if end_date > end_date_today:
            end_date = end_date_today

    x_locator_beg = '//*[@id="profit-calc-date-from-input"]'
    x_locator_end = '//*[@id="profit-calc-date-to-input"]'

    # Переход по указанному URL
    driver.get(url)

    date_info = find_start_date_element(driver)
    if date_info is None:
        print('Пропуск: не удалось найти дату старта стратегии на странице', url)
        return False
    date_str = extract_date_text(date_info)
    if date_str is None:
        print('Пропуск: не удалось прочитать дату старта стратегии на странице', url)
        return False
    date_format = "%d.%m.%Y"
    try:
        date_object = datetime.strptime(date_str, date_format)
    except ValueError:
        print("Неправильный формат даты")
        exit(1)

    if replace:
        if begin_date < date_object:
            print(
                f'Начало периода скорректировано: {begin_date:%d.%m.%Y} → {date_object:%d.%m.%Y} '
                f'(дата старта стратегии)',
            )
            begin_date = date_object
        if begin_date >= end_date:
            print('Пропуск: после корректировки период пуст')
            return False
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
        save_history_record_to_db(strategy_id, beg_set_date, perc, perc_text, replace=replace)
        last_summ = perc
        beg_set_date = end_set_date

    return True