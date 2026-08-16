from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

url = "https://www.comon.ru/strategies/"

# Создание экземпляра веб-драйвера Chrome.  Не используем Options, чтобы видеть браузер.
driver = webdriver.Chrome()

# Переход по указанному URL
driver.get(url)

# Ожидание загрузки элементов на странице (например, ждем появления хотя бы одного тега <a>)
try:
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "a"))
    )
    # Находим все div, у которых data-marker начинается с "pagination-item"
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
    print(max_number)
except:
    print("Превышено время ожидания загрузки элементов.")
