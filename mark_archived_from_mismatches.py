"""
Анализ mismatches CSV:
1) Сначала Selenium-проверка с 01.01.2026: если depo_real=1 (нулевая доходность) —
   стратегия помечается archived, остальные проверки не делаются.
2) Иначе старый алгоритм: для depo_real=1 в CSV — повторный запрос и 3 случайных периода;
   если все дают 1 — archived.
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
ZERO_INCOME_FROM = datetime(2026, 1, 1)

X_LOCATOR_BEG = '//*[@id="profit-calc-date-from-input"]'
X_LOCATOR_END = '//*[@id="profit-calc-date-to-input"]'

PROTOCOL_COLUMNS = [
    'ordinal',
    'strategy_id',
    'number',
    'name',
    'action',
    'csv_depo_real',
    'y2026_depo_real',
    'y2026_period',
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
            'По mismatches CSV: сначала проверка нулевой доходности с 01.01.2026; '
            'иначе для depo_real=1 — повтор и 3 случайных периода; при всех =1 — archived'
        ),
    )
    parser.add_argument(
        'csv_path',
        type=Path,
        help='CSV с результатами сверки (например reports/mismatches_for_reload5.csv)',
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
    """period_end — exclusive для set_period (как в mismatches CSV из test.py)."""
    set_period(driver, period_beg, period_end, X_LOCATOR_BEG, X_LOCATOR_END)
    perc, _perc_text = get_summ_perc(driver, None)
    if perc is None:
        raise ValueError('не удалось получить доходность с сайта')
    return 1.0 + float(perc) / 100.0


def zero_income_2026_period(
    period_beg: datetime,
    period_end: datetime,
    *,
    from_date: datetime = ZERO_INCOME_FROM,
    today: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    """
    Период [с начала 2026, сегодня) внутри периода из CSV.
    period_end в CSV — exclusive. None, если пересечения нет.
    """
    period_beg = to_datetime(period_beg)
    period_end = to_datetime(period_end)
    from_date = to_datetime(from_date)
    today = to_datetime(today or datetime.now())

    beg = max(period_beg, from_date)
    end = min(period_end, today)
    if beg >= end:
        return None
    return beg, end


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
                    float_fields=(
                        'csv_depo_real',
                        'y2026_depo_real',
                        'retry_depo_real',
                        'probe1_depo_real',
                        'probe2_depo_real',
                        'probe3_depo_real',
                    ),
                ),
            )


def mark_archived(record: dict, *, dry_run: bool, session, strategy_id: int, number: int, name: str, reason: str) -> dict:
    if dry_run:
        record['action'] = f'архив: {reason} (dry-run, БД не менялась)'
        record['archived'] = 'да (dry-run)'
        print(f'  -> архив (dry-run): №{number} {name} [{reason}]')
    else:
        set_strategy_archived(session, strategy_id, archived=True)
        record['action'] = f'помечена archived: {reason}'
        record['archived'] = 'да'
        print(f'  -> archived=1: №{number} {name} [{reason}]')
    return record


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
        'y2026_depo_real': '',
        'y2026_period': '',
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

    driver.get(link)
    wait_for_profit_calculator(driver)

    # 1) Прежде всего: нулевая доходность с начала 2026
    y2026 = zero_income_2026_period(period_beg, period_end)
    if y2026 is not None:
        y_beg, y_end = y2026
        record['y2026_period'] = format_period(y_beg, y_end)
        print(f'  проверка с 2026: {format_period(y_beg, y_end)}')
        y2026_depo = fetch_depo_real(driver, y_beg, y_end)
        record['y2026_depo_real'] = y2026_depo
        print(f'  2026: depo_real={y2026_depo:.6f}')
        if is_depo_real_one(y2026_depo, eps=eps):
            return mark_archived(
                record,
                dry_run=dry_run,
                session=session,
                strategy_id=strategy_id,
                number=number,
                name=name,
                reason='нулевая доходность с 01.01.2026',
            )
    else:
        print('  проверка с 2026: пропуск (нет пересечения с периодом CSV / сегодня)')

    # 2) Старый алгоритм
    if not is_depo_real_one(csv_depo_real, eps=eps):
        record['action'] = 'пропуск: depo_real≠1 (2026 не ноль)'
        return record

    print(f'  кандидат depo_real=1 — повторный запрос за {period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}')
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
        print(f'  проба {i + 1}: {format_period(beg, end)} -> depo_real={depo:.6f}')

    if all(is_depo_real_one(value, eps=eps) for value in probe_results):
        return mark_archived(
            record,
            dry_run=dry_run,
            session=session,
            strategy_id=strategy_id,
            number=number,
            name=name,
            reason='повтор и 3 пробы =1',
        )

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
    print(f'Строк: {len(rows)} (для всех — проверка с 01.01.2026; depo_real=1 в CSV: {len(candidates)})')
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
                    'y2026_depo_real': '',
                    'y2026_period': '',
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
