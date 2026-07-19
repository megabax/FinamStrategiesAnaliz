"""Сверка дневной истории стратегии: comon API vs локальная БД."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

from lib.comon_api import fetch_strategy_profit, profit_api_to_db_series
from lib.csv_export import CSV_DELIMITER, CSV_ENCODING, format_csv_record
from lib.save import create_session
from models.strategies import History, Strategy

REPORTS_DIR = Path('reports')
DEFAULT_TOLERANCE = 0.05  # процентных пунктов (Numeric(16,6) + float API)

CSV_COLUMNS = [
    'status',
    'date',
    'db_perc',
    'api_perc',
    'diff',
    'api_date',
]


def parse_date_arg(value: str) -> date:
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f'Неверный формат даты: {value}. Используйте ГГГГ-ММ-ДД или ДД.ММ.ГГГГ',
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Сверка history в БД с GET /api/v1/strategies/{number}/profit. '
            'Учитывается сдвиг: API date D ↔ БД date D-1.'
        ),
    )
    parser.add_argument(
        '-n', '--number',
        type=int,
        required=True,
        help='Номер стратегии (поле number / id на comon.ru)',
    )
    parser.add_argument(
        '--from-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Начало периода сверки (по дате БД)',
    )
    parser.add_argument(
        '--to-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Конец периода сверки (по дате БД, включительно)',
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f'Допустимая |db - api| в процентных пунктах (по умолчанию {DEFAULT_TOLERANCE})',
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=None,
        help='CSV с расхождениями (по умолчанию reports/api_vs_db_<number>_<дата>.csv)',
    )
    parser.add_argument(
        '--all-rows',
        action='store_true',
        help='Писать в CSV все дни, не только расхождения',
    )
    return parser.parse_args()


def to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def make_output_path(number: int, arg: Path | None) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    if arg is not None:
        return arg
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return REPORTS_DIR / f'api_vs_db_{number}_{stamp}.csv'


def load_db_series(session, strategy_id: int) -> dict[date, float]:
    rows = (
        session.query(History)
        .filter(History.strategy_id == strategy_id)
        .order_by(History.datetime)
        .all()
    )
    result = {}
    for row in rows:
        if row.perc_income_day is None:
            continue
        result[to_date(row.datetime)] = float(row.perc_income_day)
    return result


def in_period(day: date, from_date: date | None, to_date: date | None) -> bool:
    if from_date is not None and day < from_date:
        return False
    if to_date is not None and day > to_date:
        return False
    return True


def compare_series(
    db_series: dict[date, float],
    api_series: dict[date, float],
    *,
    from_date: date | None,
    to_date: date | None,
    tolerance: float,
) -> list[dict]:
    from datetime import timedelta

    all_days = sorted(set(db_series) | set(api_series))
    rows = []
    for day in all_days:
        if not in_period(day, from_date, to_date):
            continue
        in_db = day in db_series
        in_api = day in api_series
        db_perc = db_series.get(day)
        api_perc = api_series.get(day)

        if in_db and not in_api:
            status = 'только_в_БД'
            diff = ''
        elif in_api and not in_db:
            status = 'только_в_API'
            diff = ''
        else:
            diff_val = abs(db_perc - api_perc)
            status = 'совпало' if diff_val <= tolerance else 'расхождение'
            diff = diff_val

        rows.append({
            'status': status,
            'date': day.isoformat(),
            'db_perc': '' if db_perc is None else db_perc,
            'api_perc': '' if api_perc is None else api_perc,
            'diff': diff,
            'api_date': (day + timedelta(days=1)).isoformat(),
        })
    return rows


def write_report(path: Path, rows: list[dict], all_rows: bool) -> int:
    export = rows if all_rows else [row for row in rows if row['status'] != 'совпало']
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding=CSV_ENCODING, newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=CSV_DELIMITER)
        writer.writeheader()
        for row in export:
            writer.writerow(
                format_csv_record(row, float_fields=('db_perc', 'api_perc', 'diff')),
            )
    return len(export)


def print_summary(strategy: Strategy, rows: list[dict], tolerance: float, output: Path) -> None:
    counts = {}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    matched = counts.get('совпало', 0)
    mismatched = counts.get('расхождение', 0)
    only_db = counts.get('только_в_БД', 0)
    only_api = counts.get('только_в_API', 0)
    total = len(rows)

    print(f'Стратегия №{strategy.number}: {strategy.name}')
    print(f'Сравнено дней: {total} (tolerance={tolerance})')
    print(f'  совпало:        {matched}')
    print(f'  расхождение:    {mismatched}')
    print(f'  только в БД:    {only_db}')
    print(f'  только в API:   {only_api}')
    print(f'Отчёт: {output.resolve()}')

    if mismatched:
        print('\nТоп расхождений по |diff|:')
        top = sorted(
            (row for row in rows if row['status'] == 'расхождение'),
            key=lambda item: float(item['diff']),
            reverse=True,
        )[:10]
        for row in top:
            print(
                f"  {row['date']}: db={row['db_perc']:.6f}, "
                f"api={row['api_perc']:.6f}, diff={row['diff']:.6f}",
            )


def main() -> int:
    args = parse_args()
    session = create_session()
    try:
        strategy = session.query(Strategy).filter_by(number=args.number).first()
        if strategy is None:
            print(f'Стратегия с number={args.number} не найдена в БД')
            return 1

        print(f'Загрузка API profit для №{args.number}...')
        api_points = fetch_strategy_profit(args.number)
        api_series = profit_api_to_db_series(api_points)
        db_series = load_db_series(session, strategy.id)
        print(f'API точек: {len(api_points)} -> дней для БД: {len(api_series)}; в БД: {len(db_series)}')

        rows = compare_series(
            db_series,
            api_series,
            from_date=args.from_date,
            to_date=args.to_date,
            tolerance=args.tolerance,
        )
        if not rows:
            print('Нет дней для сравнения в выбранном периоде.')
            return 1

        output = make_output_path(args.number, args.output)
        written = write_report(output, rows, all_rows=args.all_rows)
        print_summary(strategy, rows, args.tolerance, output)
        print(f'Строк в CSV: {written}')

        bad = sum(1 for row in rows if row['status'] != 'совпало')
        return 1 if bad else 0
    finally:
        session.close()


if __name__ == '__main__':
    raise SystemExit(main())
