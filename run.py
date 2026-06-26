from lib.load import get_links_selenium
from lib.save import save_strategies_to_db


def main():
    """
    Запрашивает у пользователя URL (или использует заданный), извлекает ссылки с помощью Selenium
    и выводит их на экран.
    """
    url = "https://www.comon.ru/strategies/" # Можно заменить на input("Введите URL: ") для интерактивного ввода
    #https: // www.comon.ru / strategies /?page = 2

    links, pages_count = get_links_selenium(url)

    print("Найдено",pages_count,"страниц")

    if links:
        save_strategies_to_db(links)
    else:
        print("\nНе удалось найти ссылки на этой странице.")

    for i in range(2,pages_count+1):
        print("-------------------- Страница",i,"----------------------------------")
        links, pages_count = get_links_selenium(f"https://www.comon.ru/strategies/?page={i}")
        if links:
            save_strategies_to_db(links)
        else:
            print("\nНе удалось найти ссылки на этой странице.")


if __name__ == "__main__":
    main()

