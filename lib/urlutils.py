import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

XPath_not_found = '//*[@id="app-body"]/div/p'
DATE_PATTERN = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')
x_path_start_date = '//*[@id="app-body"]/div/div[3]/div[4]/div/div[5]/p[1]'


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
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )

        actual_text = element.text.strip().lower()
        print(f"Элемент найден. Ожидаемый текст: '{expected_text}', Фактический текст: '{actual_text}'")

        if actual_text == expected_text:
            print("Текст элемента соответствует ожидаемому.")
            return False
        else:
            print("ВНИМАНИЕ: Текст элемента НЕ соответствует ожидаемому.")
            return True

    except TimeoutException:
        print(f"Элемент по пути '{xpath}' не был обнаружен. Всё нормально.")
        return True

    except Exception as e:
        print(f"Произошла непредвиденная ошибка при поиске элемента: {e}")
        return False


def extract_date_text(element):
    date_str = (element.get_attribute('value') or element.text or '').strip()
    if DATE_PATTERN.match(date_str):
        return date_str
    return None


def _find_date_in_elements(elements):
    for element in elements:
        date_str = extract_date_text(element)
        if date_str:
            return element
    return None


def _search_in_iframes(driver, finder):
    for iframe in driver.find_elements(By.TAG_NAME, 'iframe'):
        try:
            driver.switch_to.frame(iframe)
            element = finder()
            if element is not None:
                return element
        except WebDriverException:
            pass
        finally:
            driver.switch_to.default_content()
    return None


def _save_debug_artifacts(driver, xpath):
    try:
        driver.save_screenshot('start_date_not_found.png')
    except Exception:
        pass
    try:
        with open('page_dump.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
    except Exception:
        pass

    print('Элемент с датой старта не найден. Последний XPath:', xpath)
    try:
        print('URL:', driver.current_url)
        print('Title:', driver.title)
    except Exception:
        pass


def find_start_date_element(driver, xpath=x_path_start_date, timeout=20):
    """
    Ищет дату старта стратегии на странице comon.ru.
    Сначала — поле калькулятора доходности, затем блок createdParam, затем старый XPath.
    """
    exists = check_optional_element_text(
        driver,
        XPath_not_found,
        expected_text="данная стратегия не существует",
        timeout=6,
    )
    if not exists:
        return None

    search_steps = [
        ('profit-calc-date-from-input', lambda: _find_date_in_elements([
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.ID, 'profit-calc-date-from-input')),
            ),
        ])),
        ('createdParam', lambda: _find_date_in_elements(
            driver.find_elements(By.XPATH, "//div[contains(@class,'createdParam')]//p"),
        )),
        (xpath, lambda: _find_date_in_elements([
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xpath)),
            ),
        ])),
    ]

    for step_name, finder in search_steps:
        try:
            element = finder()
            if element is not None:
                print('Дата старта найдена через:', step_name, '→', extract_date_text(element))
                return element
        except TimeoutException:
            continue

        element = _search_in_iframes(driver, finder)
        if element is not None:
            print('Дата старта найдена в iframe через:', step_name, '→', extract_date_text(element))
            return element

    _save_debug_artifacts(driver, xpath)
    return None
