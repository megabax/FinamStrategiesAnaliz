import argparse
from datetime import datetime

from selenium import webdriver

from lib.load import load_strategy_history
from lib.save import create_session
from models.strategies import Strategy


def parse_args():
    parser = argparse.ArgumentParser(
        description='Загрузка истории портфеля стратегий с comon.ru',
    )
    parser.add_argument(
        '-n', '--number',
        type=int,
        help='Номер стратегии (поле number). Без аргумента — загружаются все стратегии',
    )
    parser.add_argument(
        '--end-date',
        type=lambda s: datetime.strptime(s, '%Y-%m-%d'),
        default=None,
        metavar='ГГГГ-ММ-ДД',
        help='Конечная дата загрузки (по умолчанию — сегодня)',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    end_date = args.end_date or datetime.now()
    session = create_session()

    if args.number is not None:
        strategy = session.query(Strategy).filter(Strategy.number == args.number).first()
        if strategy is None:
            print(f'Стратегия с номером {args.number} не найдена в базе.')
            return
        strategies = [strategy]
        print(f'Загрузка истории для стратегии №{strategy.number}: {strategy.name}')
    else:
        strategies = session.query(Strategy).all()
        print(f'Загрузка истории для {len(strategies)} стратегий')

    print(f'Конечная дата загрузки: {end_date:%d.%m.%Y}')

    driver = webdriver.Chrome()
    start_date = datetime.now()
    try:
        for strategy_row in strategies:
            if not load_strategy_history(
                driver, strategy_row.link_text, session, strategy_row.id, end_date,
            ):
                print('Пропустили стратегию', strategy_row.id, f'(номер {strategy_row.number})')
            print('Прошло времени', datetime.now() - start_date)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
