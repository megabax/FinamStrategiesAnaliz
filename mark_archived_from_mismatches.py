"""
Анализ mismatches CSV: стратегии с depo_real=1 проверяются повторно.
Если повтор и три случайных периода тоже дают 1 — стратегия помечается archived.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, time, timedelta
from pathlib import Path

from lib.browser import create_chrome_driver
from lib.csv_export import (
    CSV_DELIMITER,
    CSV_ENCODING,
    format_csv_record,
    parse_decimal,
)
from lib.load import get_summ_perc, set_period
from lib.save import create_session, set_strategy_archived
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

DEPO_ONE_EPS = 1e-6
RANDOM_PROBES = 3
MIN_RANDOM_SPAN_DAYS = 1
PROTOCOL_DIR = Path('reports')

X_LOCATOR_BEG = '//*[@id="profit-calc-date-from-input"]'
X_LOCATOR_END = '//*[@id="profit-calc-date-to-input"]'

PROTOCOL_COLUMNS = [
    'ordinal',
    'strategy_id',
    'number',
    'name',
    'action',
    'csv_depo_real',
    'retry_depo_real',
    'probe1_depo_real',
    'probe2_depo_real',
    'probe3_depo_real',
    'probe1_period',
    'probe2_period',
    'probe3_period',
    'archived',
    'period_beg',
    'period_end',
    'link',
    'error',
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            'По mismatches CSV: для depo_real=1 — повторный запрос и 3 случайных периода; '
            'если все дают 1, пометить стратегию archived'
        ),
    )
    parser.add_argument(
        'csv_path',
        type=Path,
        help='CSV с результатами сверки (например reports/mismatches_for_reload4.csv)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Не писать archived в БД, только протокол',
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Seed для случайных периодов (для воспроизводимости)',
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=None,
        help='Путь к протоколу CSV (по умолчанию reports/archive_check_<дата>.csv)',
    )
    parser.add_argument(
        '--eps',
        type=float,
        default=DEPO_ONE_EPS,
        help=f'Порог |depo_real - 1| (по умолчанию {DEPO_ONE_EPS})',
    )
    return parser.parse_args()


def is_depo_real_one(value, eps=DEPO_ONE_EPS) -> bool:
    return abs(parse_decimal(value) - 1.0) <= eps


def parse_csv_date(value: str) -> datetime:
    text = value.strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f'Неверный формат даты: {value}')


def to_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return datetime.combine(value.date(), time.min)
    return datetime.combine(value, time.min)


def wait_for_profit_calculator(driver, timeout=20):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, 'profit-calc-date-from-input')),
    )


def fetch_depo_real(driver, period_beg: datetime, period_end: datetime) -> float:
    """period_end — как в mismatches CSV из test.py: exclusive для set_period."""
    set_period(driver, period_beg, period_end, X_LOCATOR_BEG, X_LOCATOR_END)
    perc, _perc_text = get_summ_perc(driver, None)
    if perc is None:
        raise ValueError('не удалось получить доходность с сайта')
    return 1.0 + float(perc) / 100.0


def random_subperiod(
    period_beg: datetime,
    period_end: datetime,
    rng: random.Random,
    min_span_days: int = MIN_RANDOM_SPAN_DAYS,
) -> tuple[datetime, datetime]:
    """Случайный подинтервал [beg, end) внутри периода из CSV (end exclusive)."""
    period_beg = to_datetime(period_beg)
    period_end = to_datetime(period_end)
    span = (period_end - period_beg).days
    if span < min_span_days:
        raise ValueError(
            f'Период слишком короткий для случайной выборки: {span} дн. '
            f'(нужно >= {min_span_days})',
        )
    if span == min_span_days:
        return period_beg, period_end

    start_offset = rng.randint(0, span - min_span_days)
    length = rng.randint(min_span_days, span - start_offset)
    beg = period_beg + timedelta(days=start_offset)
    end = beg + timedelta(days=length)
    return beg, end


def format_period(beg: datetime, end: datetime) -> str:
    return f'{beg:%d.%m.%Y}—{end:%d.%m.%Y}'


def load_mismatch_rows(path: Path) -> list[dict]:
    with path.open(encoding=CSV_ENCODING, newline='') as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        if not reader.fieldnames:
            raise ValueError(f'Пустой CSV: {path}')
        required = {'strategy_id', 'number', 'name', 'depo_real', 'period_beg', 'period_end', 'link'}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f'В CSV нет колонок: {", ".join(sorted(missing))}')
        return list(reader)


def make_protocol_path(arg_value: Path | None) -> Path:
    PROTOCOL_DIR.mkdir(exist_ok=True)
    if arg_value is not None:
        return arg_value
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return PROTOCOL_DIR / f'archive_check_{stamp}.csv'


def write_protocol(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding=CSV_ENCODING, newline='') as f:
        writer = csv.DictWriter(f, fieldnames=PROTOCOL_COLUMNS, delimiter=CSV_DELIMITER)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                format_csv_record(
                    {col: row.get(col, '') for col in PROTOCOL_COLUMNS},
                    float_fields=('csv_depo_real', 'retry_depo_real',
                                  'probe1_depo_real', 'probe2_depo_real', 'probe3_depo_real'),
                ),
            )


def process_row(driver, row, rng, eps, dry_run, session) -> dict:
    strategy_id = int(row['strategy_id'])
    number = int(row['number'])
    name = row['name']
    link = row['link']
    csv_depo_real = parse_decimal(row['depo_real'])
    period_beg = parse_csv_date(row['period_beg'])
    period_end = parse_csv_date(row['period_end'])

    record = {
        'strategy_id': strategy_id,
        'number': number,
        'name': name,
        'action': '',
        'csv_depo_real': csv_depo_real,
        'retry_depo_real': '',
        'probe1_depo_real': '',
        'probe2_depo_real': '',
        'probe3_depo_real': '',
        'probe1_period': '',
        'probe2_period': '',
        'probe3_period': '',
        'archived': 'нет',
        'period_beg': period_beg.strftime('%d.%m.%Y'),
        'period_end': period_end.strftime('%d.%m.%Y'),
        'link': link,
        'error': '',
    }

    if not is_depo_real_one(csv_depo_real, eps=eps):
        record['action'] = 'пропуск: depo_real≠1'
        return record

    print(f'  кандидат depo_real=1 — повторный запрос за {period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}')
    driver.get(link)
    wait_for_profit_calculator(driver)
    retry_depo = fetch_depo_real(driver, period_beg, period_end)
    record['retry_depo_real'] = retry_depo
    print(f'  повтор: depo_real={retry_depo:.6f}')

    if not is_depo_real_one(retry_depo, eps=eps):
        record['action'] = 'пропуск: повтор ≠1'
        return record

    probe_results = []
    for i in range(RANDOM_PROBES):
        beg, end = random_subperiod(period_beg, period_end, rng)
        depo = fetch_depo_real(driver, beg, end)
        probe_results.append(depo)
        record[f'probe{i + 1}_depo_real'] = depo
        record[f'probe{i + 1}_period'] = format_period(beg, end)
        print(f'  проба {i + 1}: {format_period(beg, end)} → depo_real={depo:.6f}')

    if all(is_depo_real_one(value, eps=eps) for value in probe_results):
        if dry_run:
            record['action'] = 'архив (dry-run, БД не менялась)'
            record['archived'] = 'да (dry-run)'
            print(f'  → архив (dry-run): №{number} {name}')
        else:
            set_strategy_archived(session, strategy_id, archived=True)
            record['action'] = 'помечена archived'
            record['archived'] = 'да'
            print(f'  → archived=1: №{number} {name}')
        return record

    record['action'] = 'пропуск: не все пробы =1'
    return record


def main() -> int:
    args = parse_args()
    if not args.csv_path.exists():
        print(f'Файл не найден: {args.csv_path}')
        return 1

    rows = load_mismatch_rows(args.csv_path)
    candidates = [row for row in rows if is_depo_real_one(row['depo_real'], eps=args.eps)]
    protocol_path = make_protocol_path(args.output)
    rng = random.Random(args.seed)

    print(f'CSV: {args.csv_path}')
    print(f'Строк: {len(rows)}, кандидатов depo_real=1: {len(candidates)}')
    if args.dry_run:
        print('Режим dry-run: в БД ничего не пишем')
    print(f'Протокол: {protocol_path}')

    session = create_session()
    driver = create_chrome_driver()
    protocol_rows = []
    archived_count = 0

    try:
        for ordinal, row in enumerate(rows, start=1):
            print(f'строка №{ordinal} из {len(rows)}: {row.get("name", "")}')
            try:
                record = process_row(
                    driver,
                    row,
                    rng=rng,
                    eps=args.eps,
                    dry_run=args.dry_run,
                    session=session,
                )
            except Exception as exc:
                record = {
                    'strategy_id': row.get('strategy_id', ''),
                    'number': row.get('number', ''),
                    'name': row.get('name', ''),
                    'action': 'ошибка',
                    'csv_depo_real': row.get('depo_real', ''),
                    'retry_depo_real': '',
                    'probe1_depo_real': '',
                    'probe2_depo_real': '',
                    'probe3_depo_real': '',
                    'probe1_period': '',
                    'probe2_period': '',
                    'probe3_period': '',
                    'archived': 'нет',
                    'period_beg': row.get('period_beg', ''),
                    'period_end': row.get('period_end', ''),
                    'link': row.get('link', ''),
                    'error': str(exc),
                }
                print(f'  ошибка: {exc}')

            record['ordinal'] = ordinal
            if record.get('archived', '').startswith('да'):
                archived_count += 1
            protocol_rows.append(record)
    finally:
        driver.quit()
        session.close()

    write_protocol(protocol_path, protocol_rows)
    print(f'Готово. Помечено архивными: {archived_count}. Протокол: {protocol_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
