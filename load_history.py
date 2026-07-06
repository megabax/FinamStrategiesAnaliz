import argparse
from datetime import datetime

from selenium import webdriver

from lib.load import load_strategy_history
from lib.save import create_session
from models.strategies import Strategy


def parse_date_arg(value):
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f'Неверный формат даты: {value}. Используйте ГГГГ-ММ-ДД или ДД.ММ.ГГГГ',
    )


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
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Конечная дата загрузки (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ). По умолчанию — сегодня',
    )
    parser.add_argument(
        '--from-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Начало периода (только с --reload)',
    )
    parser.add_argument(
        '--reload',
        action='store_true',
        help='Перезагрузить указанную стратегию за период, заменяя существующие записи',
    )
    return parser.parse_args()


def validate_args(args):
    if args.reload:
        if args.number is None:
            raise SystemExit('Режим --reload требует указать стратегию: -n/--number')
        if args.from_date is None:
            raise SystemExit('Режим --reload требует указать начало периода: --from-date')
        if args.end_date is None:
            raise SystemExit('Режим --reload требует указать конец периода: --end-date')
        if args.from_date.date() > args.end_date.date():
            raise SystemExit('--from-date не может быть позже --end-date')
        return

    if args.from_date is not None:
        raise SystemExit('--from-date используется только вместе с --reload')


def main():
    args = parse_args()
    validate_args(args)

    end_date = args.end_date or datetime.now()
    session = create_session()

    if args.number is not None:
        strategy = session.query(Strategy).filter(Strategy.number == args.number).first()
        if strategy is None:
            print(f'Стратегия с номером {args.number} не найдена в базе.')
            return
        strategies = [strategy]
        if args.reload:
            print(
                f'Перезагрузка истории для стратегии №{strategy.number}: {strategy.name}, '
                f'период {args.from_date:%d.%m.%Y} — {end_date:%d.%m.%Y}',
            )
        else:
            print(f'Загрузка истории для стратегии №{strategy.number}: {strategy.name}')
    else:
        strategies = session.query(Strategy).all()
        print(f'Загрузка истории для {len(strategies)} стратегий')

    if not args.reload:
        print(f'Конечная дата загрузки: {end_date:%d.%m.%Y}')

    driver = webdriver.Chrome()
    start_date = datetime.now()
    try:
        for strategy_row in strategies:
            if not load_strategy_history(
                driver,
                strategy_row.link_text,
                session,
                strategy_row.id,
                end_date,
                from_date=args.from_date,
                replace=args.reload,
            ):
                print('Пропустили стратегию', strategy_row.id, f'(номер {strategy_row.number})')
            print('Прошло времени', datetime.now() - start_date)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
