import requests
from bs4 import BeautifulSoup
import re

def get_links(url):
  """
  Получает HTML-контент по указанному URL и извлекает все ссылки (теги <a>).

  Args:
    url: URL веб-страницы.

  Returns:
    Список строк, представляющих собой URL-адреса, найденные на странице.
    Возвращает пустой список, если произошла ошибка или ссылки не найдены.
  """
  try:

    headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/114.0.0.0 Safari/537.36",
      "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Проверка на ошибки HTTP (например, 404)
    print(response.content)

    soup = BeautifulSoup(response.content, 'html.parser')
    links = []

    for a_tag in soup.find_all('a', href=True):  # Находим все теги <a> с атрибутом href
      href = a_tag['href']
      links.append(href)

    return links

  except requests.exceptions.RequestException as e:
    print(f"Ошибка при запросе URL: {e}")
    return []
  except Exception as e:
    print(f"Произошла ошибка: {e}")
    return []


def main():
  """
  Запрашивает у пользователя URL, извлекает ссылки и выводит их на экран.
  """
  url = "https://www.comon.ru/strategies/"

  links = get_links(url)

  if links:
    print("\nНайденные ссылки:")
    for link in links:
      print(link)
  else:
    print("\nНе удалось найти ссылки на этой странице.")


if __name__ == "__main__":
  main()
