import argparse

from lib.browser import create_chrome_driver
from lib.load import get_links_selenium
from lib.rate_limit import pause_selenium_page
from lib.save import save_strategies_to_db


def parse_args():
    parser = argparse.ArgumentParser(
        description='Загрузка списка стратегий с comon.ru в базу данных',
    )
    parser.add_argument(
        '--only-new',
        action='store_true',
        help='Не обновлять существующие стратегии, добавлять только новые',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    url = 'https://www.comon.ru/strategies/'

    total_added = 0
    total_skipped = 0

    driver = create_chrome_driver()
    try:
        links, pages_count = get_links_selenium(url, driver=driver)
        if pages_count is None:
            print('Не удалось определить число страниц.')
            return

        print('Найдено', pages_count, 'страниц')
        if args.only_new:
            print('Режим: только новые стратегии (существующие пропускаются)')

        if links:
            added, skipped = save_strategies_to_db(links, skip_existing=args.only_new)
            total_added += added
            total_skipped += skipped
        else:
            print('Не удалось найти ссылки на этой странице.')

        for i in range(2, pages_count + 1):
            pause_selenium_page()
            print('-------------------- Страница', i, '----------------------------------')
            links, _ = get_links_selenium(f'https://www.comon.ru/strategies/?page={i}', driver=driver)
            if links:
                added, skipped = save_strategies_to_db(links, skip_existing=args.only_new)
                total_added += added
                total_skipped += skipped
            else:
                print('Не удалось найти ссылки на этой странице.')
    finally:
        driver.quit()

    if args.only_new:
        print(f'Итого: добавлено {total_added}, пропущено (уже в базе) {total_skipped}')


if __name__ == '__main__':
    main()
