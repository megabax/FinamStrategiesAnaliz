"""Сравнение двух стратегий: график MA/STD как в stathist, CAGR и Sharpe."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import select

from analiz.metrics import compute_strategy_metrics
from lib.save import create_session
from models.strategies import History, Strategy

COLORS = (
    {'daily': 'skyblue', 'ma': 'C0', 'band': 'C0'},
    {'daily': 'navajowhite', 'ma': 'C1', 'band': 'C1'},
)


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
        description=(
            'Сравнение двух стратегий: дневной % с MA ± STD (как stathist.py), '
            'годовая доходность (CAGR) и Sharpe'
        ),
    )
    parser.add_argument(
        '-n', '--numbers',
        type=int,
        nargs=2,
        required=True,
        metavar=('N1', 'N2'),
        help='Номера двух стратегий на comon.ru',
    )
    parser.add_argument(
        '-w', '--window',
        type=int,
        default=100,
        help='Окно скользящего среднего и std (как в stathist, по умолчанию 100)',
    )
    parser.add_argument(
        '--from-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Начало периода (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ)',
    )
    parser.add_argument(
        '--to-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Конец периода',
    )
    parser.add_argument(
        '--risk-free-rate',
        type=float,
        default=0.0,
        metavar='RATE',
        help='Безрисковая ставка годовых, доля (например 0.16 для 16%%)',
    )
    parser.add_argument(
        '--overlap-only',
        action='store_true',
        help='Считать метрики только по пересечению дат обеих стратегий',
    )
    parser.add_argument(
        '--no-show',
        action='store_true',
        help='Не открывать окно matplotlib',
    )
    return parser.parse_args()


def load_strategy_series(session, number: int, from_date, to_date) -> tuple[Strategy, pd.DataFrame]:
    strategy = session.query(Strategy).filter(Strategy.number == number).first()
    if strategy is None:
        raise LookupError(f'Стратегия с номером {number} не найдена в базе.')

    stmt = (
        select(History.datetime, History.perc_income_day)
        .filter(History.strategy_id == strategy.id)
        .order_by(History.datetime)
    )
    if from_date is not None:
        stmt = stmt.where(History.datetime >= from_date.date())
    if to_date is not None:
        stmt = stmt.where(History.datetime <= to_date.date())

    df = pd.read_sql(stmt, session.bind)
    if df.empty:
        raise LookupError(f'Нет истории для стратегии №{strategy.number} ({strategy.name}).')

    df['datetime'] = pd.to_datetime(df['datetime'])
    df['perc_income_day'] = pd.to_numeric(df['perc_income_day'], errors='coerce')
    df = df.dropna(subset=['perc_income_day']).set_index('datetime').sort_index()
    return strategy, df


def add_stathist_bands(df: pd.DataFrame, window: int) -> pd.DataFrame:
    out = df.copy()
    out['moving_avg'] = out['perc_income_day'].rolling(window=window).mean()
    out['moving_std'] = out['perc_income_day'].rolling(window=window).std()
    out['upper_band'] = out['moving_avg'] + out['moving_std']
    out['lower_band'] = out['moving_avg'] - out['moving_std']
    return out


def fmt(value, pattern: str) -> str:
    if value is None:
        return '—'
    return format(value, pattern)


def print_comparison(rows: list[dict]) -> None:
    a, b = rows
    print()
    print(f"{'':<22}{a['label']:<32}{b['label']:<32}")
    print('-' * 86)
    for key, title, pattern in (
        ('period', 'Период', 's'),
        ('days', 'Дней', 'd'),
        ('cagr_pct', 'CAGR, %', '.3f'),
        ('sharpe', 'Sharpe', '.4f'),
        ('total_return_pct', 'Итого, %', '.3f'),
        ('volatility_pct', 'Волатильность, %', '.3f'),
        ('max_drawdown_pct', 'Max drawdown, %', '.3f'),
        ('sortino', 'Sortino', '.4f'),
        ('calmar', 'Calmar', '.4f'),
    ):
        left = a[key] if key == 'period' else fmt(a[key], pattern)
        right = b[key] if key == 'period' else fmt(b[key], pattern)
        print(f'{title:<22}{str(left):<32}{str(right):<32}')

    print()
    if a['cagr_pct'] is not None and b['cagr_pct'] is not None:
        if a['cagr_pct'] > b['cagr_pct']:
            print(f'Выше CAGR: {a["short"]}')
        elif b['cagr_pct'] > a['cagr_pct']:
            print(f'Выше CAGR: {b["short"]}')
        else:
            print('CAGR одинаковый.')
    if a['sharpe'] is not None and b['sharpe'] is not None:
        if a['sharpe'] > b['sharpe']:
            print(f'Выше Sharpe: {a["short"]}')
        elif b['sharpe'] > a['sharpe']:
            print(f'Выше Sharpe: {b["short"]}')
        else:
            print('Sharpe одинаковый.')


def plot_comparison(prepared: list[tuple[Strategy, pd.DataFrame]], window: int) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=False)
    for ax, (strategy, df), colors in zip(axes, prepared, COLORS):
        ax.plot(
            df.index, df['perc_income_day'],
            label='Процент дохода за день', color=colors['daily'], alpha=0.7,
        )
        ax.plot(
            df.index, df['moving_avg'],
            label=f'Скользящее среднее ({window} дней)',
            color=colors['ma'], linewidth=2,
        )
        ax.plot(
            df.index, df['upper_band'],
            label='Верхняя зона (MA + STD)',
            color='red', linestyle='--', alpha=0.6,
        )
        ax.plot(
            df.index, df['lower_band'],
            label='Нижняя зона (MA - STD)',
            color='green', linestyle='--', alpha=0.6,
        )
        ax.fill_between(df.index, df['lower_band'], df['upper_band'], color='gray', alpha=0.2)
        ax.set_title(f'№{strategy.number} {strategy.name}: дневной % дохода (MA ± STD, окно {window})')
        ax.set_ylabel('Процент дохода')
        ax.legend(loc='upper left')
        ax.grid(True)

    axes[-1].set_xlabel('Дата')
    fig.tight_layout()
    plt.show()


def main() -> int:
    args = parse_args()
    n1, n2 = args.numbers
    if n1 == n2:
        print('Нужны два разных номера стратегий.')
        return 1

    session = create_session()
    try:
        strategy_a, df_a = load_strategy_series(session, n1, args.from_date, args.to_date)
        strategy_b, df_b = load_strategy_series(session, n2, args.from_date, args.to_date)
    except LookupError as exc:
        print(exc)
        return 1
    finally:
        session.close()

    metric_a = df_a
    metric_b = df_b
    overlap_note = ''
    if args.overlap_only:
        common = df_a.index.intersection(df_b.index)
        if len(common) < 2:
            print('Недостаточно общих дат для сравнения (--overlap-only).')
            return 1
        metric_a = df_a.loc[common]
        metric_b = df_b.loc[common]
        overlap_note = f'метрики по пересечению дат: {common.min().date()} — {common.max().date()}'

    rows = []
    for strategy, metric_df in (
        (strategy_a, metric_a),
        (strategy_b, metric_b),
    ):
        metrics = compute_strategy_metrics(
            metric_df['perc_income_day'].tolist(),
            risk_free_rate=args.risk_free_rate,
        )
        if metrics is None:
            print(f'Недостаточно истории для №{strategy.number} ({strategy.name}).')
            return 1
        period_from = metric_df.index.min().date()
        period_to = metric_df.index.max().date()
        rows.append({
            'short': f'№{strategy.number}',
            'label': f'№{strategy.number} {strategy.name}',
            'period': f'{period_from:%d.%m.%Y} — {period_to:%d.%m.%Y}',
            **metrics,
        })

    print(f'Сравнение стратегий №{n1} и №{n2}')
    if overlap_note:
        print(overlap_note)
    print_comparison(rows)

    prepared = [
        (strategy_a, add_stathist_bands(df_a, args.window)),
        (strategy_b, add_stathist_bands(df_b, args.window)),
    ]
    if not args.no_show:
        plot_comparison(prepared, args.window)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
