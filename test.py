import csv
from datetime import datetime, time, timedelta
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import func

from lib.load import get_summ_perc, set_period
from lib.save import create_session
from models.strategies import History, Strategy

MATCH_TOLERANCE = 0.01
PROTOCOL_DIR = Path('reports')

X_LOCATOR_BEG = '//*[@id="profit-calc-date-from-input"]'
X_LOCATOR_END = '//*[@id="profit-calc-date-to-input"]'

CSV_COLUMNS = [
    'ordinal',
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
    'link',
    'error',
]


def to_datetime(value):
    if isinstance(value, datetime):
        return datetime.combine(value.date(), time.min)
    return datetime.combine(value, time.min)


def wait_for_profit_calculator(driver, timeout=20):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, 'profit-calc-date-from-input')),
    )


def compound_from_history(session, strategy_id):
    depo = 1.0
    rows = (
        session.query(History)
        .filter(History.strategy_id == strategy_id)
        .order_by(History.datetime)
        .all()
    )
    for row in rows:
        if row.perc_income_day is None:
            raise ValueError(
                f'Пустой perc_income_day для strategy_id={strategy_id}, дата {row.datetime}',
            )
        depo *= 1.0 + float(row.perc_income_day) / 100.0
    return depo, rows


def make_protocol_path():
    PROTOCOL_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return PROTOCOL_DIR / f'verify_protocol_{stamp}.csv'


def write_protocol_row(writer, row_data):
    writer.writerow(row_data)


def format_result_line(name, depo, depo_real, diff, status, period_beg, period_end, days_count):
    return (
        f'{name}: depo={depo:.6f}, depo_real={depo_real:.6f}, '
        f'diff={diff:.6f}, {status} '
        f'({period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}, дней={days_count})'
    )


def main():
    session = create_session()

    query = (
        session.query(
            History.strategy_id,
            Strategy.number,
            func.min(History.datetime).label('min_datetime'),
            func.max(History.datetime).label('max_datetime'),
            Strategy.name,
            Strategy.link_text,
        )
        .outerjoin(Strategy, History.strategy_id == Strategy.id)
        .group_by(
            History.strategy_id,
            Strategy.number,
            Strategy.name,
            Strategy.link_text,
        )
        .order_by(History.strategy_id)
    )
    results = query.all()
    total = len(results)
    protocol_path = make_protocol_path()

    driver = webdriver.Chrome()
    print('--- Результаты проверки ---')
    print(f'Стратегий к проверке: {total}')
    print(f'Протокол: {protocol_path}')

    try:
        with protocol_path.open('w', encoding='utf-8-sig', newline='') as protocol_file:
            writer = csv.DictWriter(protocol_file, fieldnames=CSV_COLUMNS, delimiter=';')
            writer.writeheader()
            protocol_file.flush()

            for ordinal, row in enumerate(results, start=1):
                print(f'стратегия №{ordinal} из {total}')

                base_record = {
                    'ordinal': ordinal,
                    'strategy_id': row.strategy_id,
                    'number': row.number,
                    'name': row.name,
                    'link': row.link_text,
                    'period_beg': '',
                    'period_end': '',
                    'days_count': '',
                    'depo': '',
                    'depo_real': '',
                    'diff': '',
                    'matched': '',
                    'status': '',
                    'error': '',
                }

                try:
                    depo, history_rows = compound_from_history(session, row.strategy_id)
                    if not history_rows:
                        record = {
                            **base_record,
                            'status': 'НЕТ ИСТОРИИ',
                            'matched': 'нет',
                            'error': 'нет записей истории',
                        }
                        write_protocol_row(writer, record)
                        protocol_file.flush()
                        print(f'{row.name}: нет записей истории')
                        continue

                    period_beg = to_datetime(row.min_datetime)
                    period_end = to_datetime(row.max_datetime) + timedelta(days=1)
                    base_record['period_beg'] = period_beg.strftime('%d.%m.%Y')
                    base_record['period_end'] = period_end.strftime('%d.%m.%Y')
                    base_record['days_count'] = len(history_rows)

                    driver.get(row.link_text)
                    wait_for_profit_calculator(driver)
                    set_period(driver, period_beg, period_end, X_LOCATOR_BEG, X_LOCATOR_END)
                    perc, perc_text = get_summ_perc(driver, None)
                    if perc is None:
                        record = {
                            **base_record,
                            'status': 'ОШИБКА',
                            'matched': 'нет',
                            'error': 'не удалось получить доходность с сайта',
                        }
                        write_protocol_row(writer, record)
                        protocol_file.flush()
                        print(f'{row.name}: не удалось получить доходность с сайта')
                        continue

                    depo_real = 1.0 + perc / 100.0
                    diff = abs(depo - depo_real)
                    matched = diff < MATCH_TOLERANCE
                    status = 'СОВПАЛО' if matched else 'РАСХОЖДЕНИЕ'

                    record = {
                        **base_record,
                        'depo': f'{depo:.6f}',
                        'depo_real': f'{depo_real:.6f}',
                        'diff': f'{diff:.6f}',
                        'matched': 'да' if matched else 'нет',
                        'status': status,
                    }
                    write_protocol_row(writer, record)
                    protocol_file.flush()

                    print(format_result_line(
                        row.name, depo, depo_real, diff, status,
                        period_beg, period_end, len(history_rows),
                    ))

                except Exception as exc:
                    record = {
                        **base_record,
                        'status': 'ОШИБКА',
                        'matched': 'нет',
                        'error': str(exc),
                    }
                    write_protocol_row(writer, record)
                    protocol_file.flush()
                    print(f'{row.name}: ошибка — {exc}')

    finally:
        driver.quit()


if __name__ == '__main__':
    main()
