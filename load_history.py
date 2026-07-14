import argparse
import sys
from datetime import datetime, timedelta

from lib.browser import create_chrome_driver
from lib.load import load_strategy_history
from lib.save import create_session, delete_strategy_history_period, get_active_strategies
from lib.verify import MATCH_TOLERANCE, HistoryVerificationError, verify_strategy_history
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
        help='Конечная дата загрузки (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ). По умолчанию — вчера',
    )
    parser.add_argument(
        '--from-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Начало периода (с --reload или --clear-and-load)',
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--reload',
        action='store_true',
        help='Перезагрузить указанную стратегию за период, заменяя существующие записи',
    )
    mode_group.add_argument(
        '--clear-and-load',
        action='store_true',
        help='Сначала удалить историю стратегии за период, затем загрузить заново',
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=MATCH_TOLERANCE,
        help=f'Допустимая абсолютная разница множителей при проверке (по умолчанию {MATCH_TOLERANCE})',
    )
    return parser.parse_args()


def validate_period_mode(args, mode_name):
    if args.number is None:
        raise SystemExit(f'Режим {mode_name} требует указать стратегию: -n/--number')
    if args.from_date is None:
        raise SystemExit(f'Режим {mode_name} требует указать начало периода: --from-date')
    if args.end_date is None:
        raise SystemExit(f'Режим {mode_name} требует указать конец периода: --end-date')
    if args.from_date.date() > args.end_date.date():
        raise SystemExit('--from-date не может быть позже --end-date')


def validate_args(args):
    if args.reload:
        validate_period_mode(args, '--reload')
        return

    if args.clear_and_load:
        validate_period_mode(args, '--clear-and-load')
        return

    if args.from_date is not None:
        raise SystemExit('--from-date используется только с --reload или --clear-and-load')


def main():
    args = parse_args()
    validate_args(args)

    end_date = args.end_date or (datetime.now() - timedelta(days=1))
    session = create_session()
    period_mode = args.reload or args.clear_and_load

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
        elif args.clear_and_load:
            print(
                f'Очистка и загрузка истории для стратегии №{strategy.number}: {strategy.name}, '
                f'период {args.from_date:%d.%m.%Y} — {end_date:%d.%m.%Y}',
            )
        else:
            print(f'Загрузка истории для стратегии №{strategy.number}: {strategy.name}')
            if strategy.archived:
                print('(архивная стратегия — обрабатывается по явному указанию номера)')
    else:
        strategies = get_active_strategies(session)
        print(f'Загрузка истории для {len(strategies)} стратегий (без архивных)')

    if not period_mode:
        print(f'Конечная дата загрузки: {end_date:%d.%m.%Y}')

    driver = create_chrome_driver()
    start_date = datetime.now()
    try:
        for strategy_row in strategies:
            if args.clear_and_load:
                deleted = delete_strategy_history_period(
                    session,
                    strategy_row.id,
                    args.from_date,
                    end_date,
                )
                print(
                    f'Удалено записей за период: {deleted} '
                    f'(strategy_id={strategy_row.id}, номер {strategy_row.number})',
                )

            loaded_period = load_strategy_history(
                driver,
                strategy_row.link_text,
                session,
                strategy_row.id,
                end_date,
                from_date=args.from_date if period_mode else None,
                replace=args.reload,
            )
            if loaded_period is None:
                print('Пропустили стратегию', strategy_row.id, f'(номер {strategy_row.number})')
            else:
                period_beg, period_end = loaded_period
                try:
                    result = verify_strategy_history(
                        driver,
                        session,
                        strategy_row,
                        period_beg,
                        period_end,
                        tolerance=args.tolerance,
                    )
                except HistoryVerificationError as exc:
                    print('ОШИБКА проверки истории:', exc)
                    sys.exit(1)
                except ValueError as exc:
                    print('ОШИБКА проверки истории:', exc)
                    sys.exit(1)

                print(
                    f'Проверка пройдена для №{strategy_row.number} ({strategy_row.name}): '
                    f'период {result.period_beg:%d.%m.%Y} — {result.period_end:%d.%m.%Y}, '
                    f'depo={result.depo:.6f}, depo_real={result.depo_real:.6f}, '
                    f'diff={result.diff:.6f}, дней={result.days_count}',
                )
            print('Прошло времени', datetime.now() - start_date)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
