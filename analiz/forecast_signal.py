"""CLI: walk-forward знак и волатильность за n дней. Не LSTM и не прогноз пути."""

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

from analiz.forecast import load_strategy_series, parse_date_arg
from lib.csv_export import write_dataframe_csv
from lib.save import create_session
from lib.walkforward import (
    BLOCK_DAYS,
    LOOKBACK,
    MIN_TRAIN_BLOCKS,
    equity_from_returns,
    follow_signal_equity,
    summarize_walkforward,
    walk_forward_signal,
)
from models.strategies import Strategy

REPORTS_DIR = Path('reports')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Walk-forward: знак роста/падения и волатильность следующего блока из n дней. '
            'Расширяющееся окно (не сплит 50/50). Сравнение с наивными правилами. '
            'Не рисует «предсказанный путь» LSTM.'
        ),
    )
    parser.add_argument('-n', '--number', type=int, required=True, help='Номер стратегии')
    parser.add_argument(
        '-b', '--block',
        type=int,
        default=BLOCK_DAYS,
        help=f'Горизонт блока в днях (по умолчанию {BLOCK_DAYS})',
    )
    parser.add_argument(
        '-w', '--lookback',
        type=int,
        default=LOOKBACK,
        help=f'Окно признаков до старта блока (по умолчанию {LOOKBACK})',
    )
    parser.add_argument(
        '--min-train-blocks',
        type=int,
        default=MIN_TRAIN_BLOCKS,
        help=f'Минимум прошлых блоков до первой линейной модели (по умолчанию {MIN_TRAIN_BLOCKS})',
    )
    parser.add_argument('--from-date', type=parse_date_arg, default=None, metavar='ДАТА')
    parser.add_argument('--to-date', type=parse_date_arg, default=None, metavar='ДАТА')
    parser.add_argument('--output', default=None, metavar='ФАЙЛ')
    parser.add_argument('--no-show', action='store_true')
    return parser.parse_args()


def make_output_path(arg_value: str | None, number: int) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    if arg_value:
        return Path(arg_value)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return REPORTS_DIR / f'forecast_signal_{number}_{stamp}.csv'


def fmt(value, pattern: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return '—'
    return format(value, pattern)


def print_report(strategy: Strategy, series: pd.Series, wf: pd.DataFrame, summary: dict, args) -> None:
    print(f'Стратегия №{strategy.number}: {strategy.name}')
    print(
        f'История: {series.index.min():%d.%m.%Y} — {series.index.max():%d.%m.%Y}, '
        f'{len(series)} дней',
    )
    print(
        f'Walk-forward: {summary["period_from"]:%d.%m.%Y} — {summary["period_to"]:%d.%m.%Y}, '
        f'{summary["blocks"]} блоков по {args.block} дн., lookback={args.lookback}',
    )
    print()
    print('Направление блока (рост/падение), не путь портфеля:')
    print(f'  Линейная модель:     {fmt(summary["linear_dir_pct"], ".1f")}%')
    print(f'  Наивный MA:          {fmt(summary["naive_ma_dir_pct"], ".1f")}%')
    print(f'  Наивный прошлый блок:{fmt(summary["naive_last_dir_pct"], ".1f")}%')
    print(f'  Наивный знак среднего:{fmt(summary["naive_mean_dir_pct"], ".1f")}%')
    print()
    print('Волатильность блока (std дневного %):')
    print(
        f'  MAE прогноза vol: {fmt(summary["vol_mae"], ".4f")}  '
        f'(константа = среднее факта: {fmt(summary["vol_mae_mean"], ".4f")})',
    )
    best = max(
        ('linear', summary['linear_dir_pct']),
        ('naive_ma', summary['naive_ma_dir_pct']),
        ('naive_last', summary['naive_last_dir_pct']),
        ('naive_mean', summary['naive_mean_dir_pct']),
        key=lambda item: item[1] if item[1] == item[1] else -1,
    )
    print()
    if summary['linear_dir_pct'] > max(
        summary['naive_ma_dir_pct'],
        summary['naive_last_dir_pct'],
        summary['naive_mean_dir_pct'],
    ):
        print('Линейная модель бьёт наивных по направлению на этом ряду.')
    else:
        print(
            f'Линейная модель не лучше наивных. Лучший знак: {best[0]} '
            f'({fmt(best[1], ".1f")}%). LSTM путь здесь не чинится — другая задача.',
        )


def plot_signal(strategy: Strategy, series: pd.Series, wf: pd.DataFrame) -> None:
    actual_eq = equity_from_returns(series)
    signal_eq = follow_signal_equity(series, wf, signal_col='linear_dir')
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True)

    axes[0].plot(actual_eq.index, actual_eq.to_numpy(), color='black', linewidth=1.6, label='Портфель факт')
    axes[0].plot(
        signal_eq.index, signal_eq.to_numpy(),
        color='C0', linewidth=1.4, label='Следовать знаку линейной модели (лонг/кэш)',
    )
    if not wf.empty:
        axes[0].axvline(wf['from'].iloc[0], color='black', linestyle='--', linewidth=1, label='Старт walk-forward')
    axes[0].set_title(f'№{strategy.number} {strategy.name}: знак и vol, не прогноз пути')
    axes[0].set_ylabel('Портфель (старт = 1)')
    axes[0].legend(loc='upper left')
    axes[0].grid(True)

    axes[1].plot(wf['to'], wf['actual_vol'], color='black', linewidth=1.3, label='Факт vol блока')
    axes[1].plot(wf['to'], wf['pred_vol'], color='C1', linewidth=1.3, label='Прогноз vol')
    colors = ['C2' if int(a) == int(p) else 'C3' for a, p in zip(wf['actual_dir'], wf['linear_dir'])]
    axes[1].scatter(wf['to'], wf['actual_vol'], c=colors, s=28, zorder=3, label='Верный / неверный знак')
    axes[1].set_xlabel('Конец блока')
    axes[1].set_ylabel('Std дневного %')
    axes[1].legend(loc='upper left')
    axes[1].grid(True)

    fig.tight_layout()
    plt.show()


def main() -> int:
    args = parse_args()
    if args.block < 1 or args.lookback < 2 or args.min_train_blocks < 1:
        print('block ≥ 1, lookback ≥ 2, min-train-blocks ≥ 1.')
        return 1

    session = create_session()
    try:
        strategy, series = load_strategy_series(session, args.number, args.from_date, args.to_date)
    except LookupError as exc:
        print(exc)
        return 1
    finally:
        session.close()

    try:
        wf = walk_forward_signal(
            series,
            block_days=args.block,
            lookback=args.lookback,
            min_train_blocks=args.min_train_blocks,
        )
    except ValueError as exc:
        print(exc)
        return 1

    summary = summarize_walkforward(wf)
    print_report(strategy, series, wf, summary, args)

    export = wf.copy()
    export['from'] = pd.to_datetime(export['from']).dt.strftime('%Y-%m-%d')
    export['to'] = pd.to_datetime(export['to']).dt.strftime('%Y-%m-%d')
    output_path = make_output_path(args.output, strategy.number)
    write_dataframe_csv(export, output_path)
    print(f'CSV: {output_path.resolve()}')

    if not args.no_show:
        plot_signal(strategy, series, wf)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
