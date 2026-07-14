import argparse
import csv
from datetime import datetime, time, timedelta
from pathlib import Path

from lib.browser import create_chrome_driver
from lib.csv_export import CSV_DELIMITER, CSV_ENCODING, format_csv_record
from lib.load import get_summ_perc, set_period
from lib.save import create_session
from models.strategies import History, Strategy
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

MATCH_TOLERANCE = 0.01
PROTOCOL_DIR = Path('reports')

X_LOCATOR_BEG = '//*[@id="profit-calc-date-from-input"]'
X_LOCATOR_END = '//*[@id="profit-calc-date-to-input"]'

CSV_COLUMNS = [
    'interval_ordinal',
    'intervals_total',
    'strategy_id',
    'number',
    'name',
    'status',
    'matched',
    'depo',
    'depo_real',
    'diff',
    'period_beg',
    'period_end',
    'days_count',
    'interval_days',
    'link',
    'error',
]


def parse_date_arg(value):
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f'Неверный формат даты: {value}. Используйте ГГГГ-ММ-ДД или ДД.ММ.ГГГГ',
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description='Сверка накопительного итога по интервалам истории одной стратегии',
    )
    parser.add_argument(
        '-n', '--number',
        type=int,
        required=True,
        help='Номер стратегии (поле number)',
    )
    parser.add_argument(
        '-d', '--days',
        type=int,
        required=True,
        help='Размер интервала в днях (например, 200)',
    )
    parser.add_argument(
        '--from-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Начало периода сверки (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ). По умолчанию — с первой записи',
    )
    parser.add_argument(
        '--to-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Конец периода сверки (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ). По умолчанию — до последней записи',
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=MATCH_TOLERANCE,
        help=f'Допустимая абсолютная разница множителей (по умолчанию {MATCH_TOLERANCE})',
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=None,
        help='Путь к CSV-файлу (по умолчанию reports/verify_intervals_<номер>_<дата>.csv)',
    )
    return parser.parse_args()


def to_datetime(value):
    if isinstance(value, datetime):
        return datetime.combine(value.date(), time.min)
    return datetime.combine(value, time.min)


def wait_for_profit_calculator(driver, timeout=20):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, 'profit-calc-date-from-input')),
    )


def load_history_rows(session, strategy_id, from_date=None, to_date=None):
    query = (
        session.query(History)
        .filter(History.strategy_id == strategy_id)
        .order_by(History.datetime)
    )
    if from_date is not None:
        query = query.filter(History.datetime >= from_date)
    if to_date is not None:
        query = query.filter(History.datetime <= to_date)
    return query.all()


def split_into_chunks(rows, chunk_size):
    for index in range(0, len(rows), chunk_size):
        yield rows[index:index + chunk_size]


def compound_rows(rows):
    depo = 1.0
    for row in rows:
        if row.perc_income_day is None:
            raise ValueError(f'Пустой perc_income_day для даты {row.datetime}')
        depo *= 1.0 + float(row.perc_income_day) / 100.0
    return depo


def make_output_path(strategy_number):
    PROTOCOL_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return PROTOCOL_DIR / f'verify_intervals_{strategy_number}_{stamp}.csv'


def main():
    args = parse_args()
    if args.days <= 0:
        raise SystemExit('Размер интервала --days должен быть больше 0')
    if args.from_date and args.to_date and args.from_date > args.to_date:
        raise SystemExit('--from-date не может быть позже --to-date')

    session = create_session()
    strategy = session.query(Strategy).filter(Strategy.number == args.number).first()
    if strategy is None:
        raise SystemExit(f'Стратегия с номером {args.number} не найдена в базе.')

    history_rows = load_history_rows(
        session, strategy.id, args.from_date, args.to_date,
    )
    if not history_rows:
        if args.from_date or args.to_date:
            beg = args.from_date.strftime('%d.%m.%Y') if args.from_date else '…'
            end = args.to_date.strftime('%d.%m.%Y') if args.to_date else '…'
            period_hint = f' в периоде {beg} — {end}'
        else:
            period_hint = ''
        raise SystemExit(f'У стратегии №{args.number} нет записей истории{period_hint}.')

    chunks = list(split_into_chunks(history_rows, args.days))
    intervals_total = len(chunks)
    output_path = args.output or make_output_path(args.number)

    print('--- Сверка по интервалам ---')
    print(f'Стратегия №{strategy.number}: {strategy.name}')
    period_from = history_rows[0].datetime
    period_to = history_rows[-1].datetime
    print(
        f'Период: {period_from:%d.%m.%Y} — {period_to:%d.%m.%Y}, '
        f'записей: {len(history_rows)}, интервал: {args.days} дн., сравнений: {intervals_total}',
    )
    print(f'Протокол: {output_path}')

    driver = create_chrome_driver()
    try:
        driver.get(strategy.link_text)
        wait_for_profit_calculator(driver)

        with output_path.open('w', encoding=CSV_ENCODING, newline='') as protocol_file:
            writer = csv.DictWriter(protocol_file, fieldnames=CSV_COLUMNS, delimiter=CSV_DELIMITER)
            writer.writeheader()
            protocol_file.flush()

            for ordinal, chunk in enumerate(chunks, start=1):
                print(f'интервал №{ordinal} из {intervals_total}')

                period_beg = to_datetime(chunk[0].datetime)
                period_end = to_datetime(chunk[-1].datetime) + timedelta(days=1)

                base_record = {
                    'interval_ordinal': ordinal,
                    'intervals_total': intervals_total,
                    'strategy_id': strategy.id,
                    'number': strategy.number,
                    'name': strategy.name,
                    'link': strategy.link_text,
                    'period_beg': period_beg.strftime('%d.%m.%Y'),
                    'period_end': period_end.strftime('%d.%m.%Y'),
                    'days_count': len(chunk),
                    'interval_days': args.days,
                    'depo': '',
                    'depo_real': '',
                    'diff': '',
                    'matched': '',
                    'status': '',
                    'error': '',
                }

                try:
                    depo = compound_rows(chunk)
                    set_period(driver, period_beg, period_end, X_LOCATOR_BEG, X_LOCATOR_END)
                    perc, perc_text = get_summ_perc(driver, None)
                    if perc is None:
                        record = {
                            **base_record,
                            'status': 'ОШИБКА',
                            'matched': 'нет',
                            'error': 'не удалось получить доходность с сайта',
                        }
                        writer.writerow(record)
                        protocol_file.flush()
                        print(f'  {period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}: не удалось получить доходность с сайта')
                        continue

                    depo_real = 1.0 + perc / 100.0
                    diff = abs(depo - depo_real)
                    matched = diff < args.tolerance
                    status = 'СОВПАЛО' if matched else 'РАСХОЖДЕНИЕ'

                    record = format_csv_record({
                        **base_record,
                        'depo': depo,
                        'depo_real': depo_real,
                        'diff': diff,
                        'matched': 'да' if matched else 'нет',
                        'status': status,
                    }, float_fields=('depo', 'depo_real', 'diff'))
                    writer.writerow(record)
                    protocol_file.flush()

                    print(
                        f'  {period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}, '
                        f'дней={len(chunk)}: depo={depo:.6f}, depo_real={depo_real:.6f}, '
                        f'diff={diff:.6f}, {status}',
                    )

                except Exception as exc:
                    record = {
                        **base_record,
                        'status': 'ОШИБКА',
                        'matched': 'нет',
                        'error': str(exc),
                    }
                    writer.writerow(record)
                    protocol_file.flush()
                    print(f'  {period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}: ошибка — {exc}')

    finally:
        driver.quit()


if __name__ == '__main__':
    main()
