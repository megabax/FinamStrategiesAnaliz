from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

XPath_not_found = '//*[@id="app-body"]/div/p'


def check_optional_element_text(driver, xpath=XPath_not_found, expected_text="Текст для проверки", timeout=5):
    """
    Проверяет существование элемента по XPath в течение timeout секунд.
    Если элемент найден, проверяет его текст.
    Если элемент НЕ найден (сработал TimeoutException), считается, что всё нормально.

    Возвращает True, если:
    1. Элемент не найден (TimeoutException).
    2. Элемент найден, и его текст соответствует expected_text.

    Возвращает False, если:
    1. Элемент найден, но его текст НЕ соответствует expected_text.
    """
    print(f"Попытка найти элемент: {xpath}")

    try:
        # Явное ожидание (Presence)
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )

        # Элемент найден. Проверяем текст.
        actual_text = element.text.strip().lower()
        print(f"Элемент найден. Ожидаемый текст: '{expected_text}', Фактический текст: '{actual_text}'")

        if actual_text == expected_text:
            print("Текст элемента соответствует ожидаемому.")
            return False
        else:
            print("ВНИМАНИЕ: Текст элемента НЕ соответствует ожидаемому.")
            return True

    except TimeoutException:
        # Элемент не найден в течение установленного времени.
        # Это считается нормальным исходом согласно условию задачи.
        print(f"Элемент по пути '{xpath}' не был обнаружен. Всё нормально.")
        return True

    except Exception as e:
        # Обработка других возможных ошибок Selenium (кроме Timeout)
        print(f"Произошла непредвиденная ошибка при поиске элемента: {e}")
        return False


x_path_start_date = '//*[@id="app-body"]/div/div[3]/div[4]/div/div[5]/p[1]'

def find_start_date_element(driver, xpath=x_path_start_date, timeout=12):
    """
    Попытаться найти элемент:
    1) обычное ожидание presence/visibility в текущем контексте;
    2) если не найдено — пробуем искать внутри <iframe> (итеративно);
    3) если всё ещё не найдено — сохраняем скриншот и дамп HTML для отладки и возвращаем None.
    """

    XPath_not_found='//*[@id="app-body"]/div/p'
    exists = check_optional_element_text(driver, XPath_not_found, expected_text="данная стратегия не существует",
                                         timeout=6
                                         )
    if not exists:
        return None
    try:
        # сначала обычное явное ожидание (presence или visibility по необходимости)
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        # при желании можно применять visibility_of_element_located вместо presence_of_element_located
        return el
    except TimeoutException:
        # элемент не найден в текущем документе — попробуем поиск в iframe'ах
        for iframe in driver.find_elements(By.TAG_NAME, 'iframe'):
            try:
                driver.switch_to.frame(iframe)
                els = driver.find_elements(By.XPATH, xpath)
                if els:
                    return els[0]
            except WebDriverException:
                # некоторые iframe могут быть недоступны (cross-origin и т.п.)
                pass
            finally:
                driver.switch_to.default_content()

        # для отладки: сохранить скрин и дамп HTML
        try:
            driver.save_screenshot('start_date_not_found.png')
        except Exception:
            pass
        try:
            with open('page_dump.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
        except Exception:
            pass

        # полезная отладочная информация
        print('Элемент с XPath не найден:', xpath)
        try:
            print('URL:', driver.current_url)
            print('Title:', driver.title)
        except Exception:
            pass

        return None

# # Использование:
# date_info = find_start_date_element(driver)
# if date_info is None:
#     # обработка ситуации — лог, пропуск, повторная попытка и т.д.
#     print('Не удалось получить date_info')
# else:
#     # элемент найден — можно читать текст
#     start_date_text = date_info.text
#     print('Start date:', start_date_text)

