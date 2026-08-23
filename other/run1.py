from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options  # Импорт Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_links_selenium(url):
    """
    Получает HTML-контент по указанному URL с помощью Selenium и извлекает все ссылки (теги <a>).

    Args:
        url: URL веб-страницы.

    Returns:
        Список строк, представляющих собой URL-адреса, найденные на странице.
        Возвращает пустой список, если произошла ошибка или ссылки не найдены.
    """
    try:
        # Настройка Chrome options для работы в режиме без графического интерфейса (headless)
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Запуск Chrome в headless режиме
        chrome_options.add_argument("--disable-gpu") # Отключение GPU, может помочь на некоторых системах
        chrome_options.add_argument("--no-sandbox") # Требуется в некоторых окружениях (например, Docker)
        chrome_options.add_argument("--disable-dev-shm-usage") # Предотвращает сбои с общей памятью

        # Создание экземпляра веб-драйвера Chrome
        driver = webdriver.Chrome(options=chrome_options)  # Указываем options здесь

        # Переход по указанному URL
        driver.get(url)

        # Ожидание загрузки элементов на странице (например, ждем появления хотя бы одного тега <a>)
        try:
          WebDriverWait(driver, 10).until(
              EC.presence_of_element_located((By.TAG_NAME, "a"))
          )
        except:
          print("Превышено время ожидания загрузки элементов.")
          return []

        # Поиск всех тегов <a> на странице
        a_tags = driver.find_elements(By.TAG_NAME, "a")

        # Извлечение атрибутов 'href' из найденных тегов <a>
        links = [a_tag.get_attribute("href") for a_tag in a_tags if a_tag.get_attribute("href") is not None] #Убираем None

        return links

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return []
    finally:
        # Закрытие веб-драйвера, чтобы освободить ресурсы
        try:
            driver.quit()
        except:
            pass # Ignore errors during driver.quit()

def main():
    """
    Запрашивает у пользователя URL (или использует заданный), извлекает ссылки с помощью Selenium
    и выводит их на экран.
    """
    url = "https://www.comon.ru/strategies/" # Можно заменить на input("Введите URL: ") для интерактивного ввода

    links = get_links_selenium(url)

    if links:
        print("\nНайденные ссылки:")
        for link in links:
            print(link)
    else:
        print("\nНе удалось найти ссылки на этой странице.")


if __name__ == "__main__":
    main()
