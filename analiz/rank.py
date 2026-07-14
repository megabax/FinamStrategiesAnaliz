"""CLI: рейтинг стратегий по метрикам доходности и риска."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from analiz.metrics import compute_metrics_dataframe, load_history_from_db, load_strategies_from_db
from lib.csv_export import write_dataframe_csv
from lib.save import create_session

REPORTS_DIR = Path('reports')

RANK_COLUMNS = [
    'rank',
    'strategy_id',
    'number',
    'name',
    'kind',
    'subscribers',
    'annual_income',
    'min_summa',
    'period_from',
    'period_to',
    'days',
    'total_return_pct',
    'cagr_pct',
    'volatility_pct',
    'max_drawdown_pct',
    'sharpe',
    'sortino',
    'calmar',
    'positive_days_pct',
    'link_text',
]

SORT_CHOICES = {
    'sharpe': ('sharpe', False),
    'sortino': ('sortino', False),
    'calmar': ('calmar', False),
    'cagr': ('cagr_pct', False),
    'return': ('total_return_pct', False),
}


def parse_date_arg(value: str) -> datetime:
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f'Неверный формат даты: {value}. Используйте ГГГГ-ММ-ДД или ДД.ММ.ГГГГ',
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Рейтинг стратегий по метрикам доходности и риска (данные из БД)',
    )
    parser.add_argument(
        '--from-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Начало периода (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ). По умолчанию — с первой записи',
    )
    parser.add_argument(
        '--to-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Конец периода. По умолчанию — по последнюю запись',
    )
    parser.add_argument(
        '--top',
        type=int,
        default=None,
        metavar='N',
        help='Вывести только топ-N строк (после сортировки)',
    )
    parser.add_argument(
        '--sort-by',
        choices=list(SORT_CHOICES),
        default='sharpe',
        help='Поле для сортировки (по умолчанию sharpe)',
    )
    parser.add_argument(
        '--min-days',
        type=int,
        default=252,
        help='Минимум торговых дней в периоде (по умолчанию 252)',
    )
    parser.add_argument(
        '--risk-free-rate',
        type=float,
        default=0.0,
        metavar='RATE',
        help='Безрисковая ставка годовых, доля (например 0.16 для 16%%)',
    )
    parser.add_argument(
        '--kind',
        default=None,
        help='Фильтр по типу стратегии (консервативный, умеренный, агрессивный)',
    )
    parser.add_argument(
        '--min-summa',
        type=int,
        default=None,
        metavar='СУММА',
        help='Минимальная сумма входа (>= указанного значения)',
    )
    parser.add_argument(
        '--include-archived',
        action='store_true',
        help='Включать архивные стратегии',
    )
    parser.add_argument(
        '--output',
        default=None,
        metavar='ФАЙЛ',
        help='Путь к CSV (по умолчанию reports/rank_<дата>.csv)',
    )
    return parser.parse_args()


def make_output_path(arg_value: str | None) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    if arg_value:
        return Path(arg_value)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return REPORTS_DIR / f'rank_{stamp}.csv'


def format_period(from_date, to_date) -> str:
    if from_date and to_date:
        return f'{from_date:%d.%m.%Y} — {to_date:%d.%m.%Y}'
    if from_date:
        return f'с {from_date:%d.%m.%Y}'
    if to_date:
        return f'по {to_date:%d.%m.%Y}'
    return 'вся доступная история'


def print_top_table(df: pd.DataFrame, limit: int = 10) -> None:
    display_cols = [
        'rank', 'number', 'name', 'days', 'cagr_pct', 'max_drawdown_pct', 'sharpe', 'calmar',
    ]
    available = [col for col in display_cols if col in df.columns]
    print(df[available].head(limit).to_string(index=False))


def main() -> int:
    args = parse_args()
    sort_col, ascending = SORT_CHOICES[args.sort_by]

    session = create_session()
    started = time.perf_counter()
    try:
        strategies_df = load_strategies_from_db(
            session,
            exclude_archived=not args.include_archived,
            kind_name=args.kind,
            min_summa=args.min_summa,
        )
        allowed_ids = set(strategies_df['strategy_id'].tolist()) if not strategies_df.empty else None

        history_df = load_history_from_db(session, args.from_date, args.to_date)
        metrics_df = compute_metrics_dataframe(
            history_df,
            strategies_df=strategies_df,
            min_days=args.min_days,
            risk_free_rate=args.risk_free_rate,
            strategy_ids=allowed_ids,
        )
    finally:
        session.close()

    elapsed = time.perf_counter() - started

    if metrics_df.empty:
        print('Нет стратегий, подходящих под фильтры и минимальную длину истории.')
        return 1

    metrics_df = metrics_df.sort_values(
        by=sort_col,
        ascending=ascending,
        na_position='last',
    ).reset_index(drop=True)
    metrics_df.insert(0, 'rank', metrics_df.index + 1)

    total_count = len(metrics_df)
    display_df = metrics_df.head(args.top) if args.top is not None else metrics_df

    output_path = make_output_path(args.output)
    export_df = display_df.reindex(columns=[col for col in RANK_COLUMNS if col in display_df.columns])
    write_dataframe_csv(export_df, output_path)

    print(f'Период: {format_period(args.from_date, args.to_date)}')
    if args.top is not None and args.top < total_count:
        print(
            f'Стратегий в рейтинге: {total_count} '
            f'(в CSV/консоль — топ {len(display_df)}, min_days={args.min_days}, sort={args.sort_by})',
        )
    else:
        print(f'Стратегий в рейтинге: {total_count} (min_days={args.min_days}, sort={args.sort_by})')
    print(f'Время расчёта: {elapsed:.2f} с')
    print(f'CSV: {output_path.resolve()}')
    print()
    print_top_table(display_df)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
