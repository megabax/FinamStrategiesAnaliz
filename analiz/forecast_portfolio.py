"""CLI: LSTM на 1-й половине, на 2-й — рекурсивные блоки по n дней и график портфеля."""

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
from lib.nnlib import (
    BATCH_SIZE,
    BLOCK_DAYS,
    DROPOUT,
    EPOCHS,
    LSTM_UNITS,
    PORTFOLIO_WINDOW,
    RANDOM_SEED,
    TRAIN_RATIO,
    run_lstm_portfolio_forecast,
)
from lib.save import create_session
from models.strategies import Strategy

REPORTS_DIR = Path('reports')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'LSTM: обучение на первой половине. На второй каждый блок из n дней '
            'предсказывается целиком по фактическому окну (MA/STD/импульс + LSTM). '
            'На графике — состояние портфеля.'
        ),
    )
    parser.add_argument(
        '-n', '--number',
        type=int,
        required=True,
        help='Номер стратегии (поле number на comon.ru)',
    )
    parser.add_argument(
        '-b', '--block',
        type=int,
        default=BLOCK_DAYS,
        help=f'Длина блока прогноза в днях (по умолчанию {BLOCK_DAYS})',
    )
    parser.add_argument(
        '--train-ratio',
        type=float,
        default=TRAIN_RATIO,
        help='Доля первой половины (обучение), по умолчанию 0.5',
    )
    parser.add_argument(
        '-w', '--window',
        type=int,
        default=PORTFOLIO_WINDOW,
        help=f'Длина look-back окна LSTM (по умолчанию {PORTFOLIO_WINDOW})',
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=EPOCHS,
        help=f'Максимум эпох (по умолчанию {EPOCHS})',
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=BATCH_SIZE,
        help=f'Размер батча (по умолчанию {BATCH_SIZE})',
    )
    parser.add_argument(
        '--units',
        type=int,
        default=LSTM_UNITS,
        help=f'Число LSTM-нейронов (по умолчанию {LSTM_UNITS})',
    )
    parser.add_argument(
        '--dropout',
        type=float,
        default=DROPOUT,
        help=f'Dropout (по умолчанию {DROPOUT})',
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=RANDOM_SEED,
        help=f'Seed (по умолчанию {RANDOM_SEED})',
    )
    parser.add_argument(
        '--from-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Начало истории (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ)',
    )
    parser.add_argument(
        '--to-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Конец истории',
    )
    parser.add_argument(
        '--output',
        default=None,
        metavar='ФАЙЛ',
        help='CSV портфель факт/прогноз (по умолчанию reports/forecast_portfolio_<number>_<дата>.csv)',
    )
    parser.add_argument(
        '--no-show',
        action='store_true',
        help='Не открывать окно matplotlib',
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Не печатать прогресс Keras',
    )
    return parser.parse_args()


def make_output_path(arg_value: str | None, number: int) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    if arg_value:
        return Path(arg_value)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return REPORTS_DIR / f'forecast_portfolio_{number}_{stamp}.csv'


def fmt(value, pattern: str) -> str:
    if value is None:
        return '—'
    return format(value, pattern)


def print_report(strategy: Strategy, series: pd.Series, result, args) -> None:
    split = result.split
    m = result.metrics
    print(f'Стратегия №{strategy.number}: {strategy.name}')
    print(
        f'История: {series.index.min():%d.%m.%Y} — {series.index.max():%d.%m.%Y}, '
        f'{len(series)} дней',
    )
    print(
        f'Обучение: {split.train_from:%d.%m.%Y} — {split.train_to:%d.%m.%Y}, '
        f'{len(split.train)} дней',
    )
    print(
        f'Тест:     {split.test_from:%d.%m.%Y} — {split.test_to:%d.%m.%Y}, '
        f'{len(split.test)} дней',
    )
    print(
        f'Блок={args.block} дн. (прямой прогноз n дней с фактического окна, затем сброс), '
        f'окно={args.window}, эпохи≤{args.epochs}, блоков={m["blocks"]}',
    )
    print()
    print('Качество состояния портфеля на тесте (старт блока = факт):')
    print(f'  MAE equity:  {fmt(m["mae"], ".4f"):<10} наивный (локальное среднее): {fmt(m["mae_naive"], ".4f")}')
    print(f'  RMSE equity: {fmt(m["rmse"], ".4f")}')
    print(f'  Corr equity: {fmt(m["corr"], ".4f")}')
    print(
        f'  Направление блока (рост/падение за n дней): '
        f'LSTM {fmt(m["block_dir_pct"], ".1f")}%  наивный {fmt(m["block_dir_pct_naive"], ".1f")}%',
    )
    print(
        f'  Портфель в конце последнего блока: факт {fmt(m["actual_end"], ".4f")}, '
        f'прогноз {fmt(m["predicted_end"], ".4f")} '
        f'(ошибка {fmt(m["end_error_pct"], ".3f")}%)',
    )


def iter_block_segments(result, start_equity: float = 1.0):
    split = result.split
    n = len(split.test)
    for i in range(0, n, result.block_days):
        j = min(i + result.block_days, n)
        if i == 0:
            dates = [split.train_to, *split.test.index[i:j]]
            actual = [start_equity, *result.actual_equity[i:j]]
            predicted = [start_equity, *result.predicted_equity[i:j]]
        else:
            dates = [split.test.index[i - 1], *split.test.index[i:j]]
            actual = [result.actual_equity[i - 1], *result.actual_equity[i:j]]
            predicted = [result.actual_equity[i - 1], *result.predicted_equity[i:j]]
        yield dates, actual, predicted


def plot_portfolio(strategy: Strategy, result) -> None:
    split = result.split
    fig, ax = plt.subplots(figsize=(14, 8))

    plot_dates = [split.train_to, *split.test.index]
    plot_actual = [1.0, *result.actual_equity]
    ax.plot(plot_dates, plot_actual, color='black', linewidth=1.8, label='Портфель факт')

    naive_segments_drawn = False
    for idx, (dates, _actual, predicted) in enumerate(iter_block_segments(result)):
        ax.plot(
            dates,
            predicted,
            color='C1',
            linewidth=1.6,
            label='Портфель LSTM (блок n дней)' if idx == 0 else None,
        )

    if result.naive_equity is not None:
        n = len(split.test)
        for i in range(0, n, result.block_days):
            j = min(i + result.block_days, n)
            if i == 0:
                dates = [split.train_to, *split.test.index[i:j]]
                naive = [1.0, *result.naive_equity[i:j]]
            else:
                dates = [split.test.index[i - 1], *split.test.index[i:j]]
                naive = [result.actual_equity[i - 1], *result.naive_equity[i:j]]
            ax.plot(
                dates,
                naive,
                color='gray',
                linestyle='--',
                linewidth=1.0,
                alpha=0.85,
                label='Наивный (локальное среднее)' if not naive_segments_drawn else None,
            )
            naive_segments_drawn = True

    for i in range(result.block_days, len(split.test), result.block_days):
        ax.axvline(split.test.index[i], color='gray', linestyle=':', alpha=0.5)

    ax.axvline(split.test_from, color='black', linestyle='--', linewidth=1, label='Начало теста')
    ax.set_title(
        f'№{strategy.number} {strategy.name}: состояние портфеля, '
        f'прогноз блоками по {result.block_days} дн.',
    )
    ax.set_xlabel('Дата')
    ax.set_ylabel('Состояние портфеля (старт теста = 1)')
    ax.legend(loc='upper left')
    ax.grid(True)
    fig.tight_layout()
    plt.show()


def main() -> int:
    args = parse_args()
    if not 0.0 < args.train_ratio < 1.0:
        print('train-ratio должен быть в интервале (0, 1).')
        return 1
    if args.window < 2 or args.block < 1:
        print('window ≥ 2, block ≥ 1.')
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
        result = run_lstm_portfolio_forecast(
            series,
            train_ratio=args.train_ratio,
            window_size=args.window,
            block_days=args.block,
            epochs=args.epochs,
            batch_size=args.batch_size,
            units=args.units,
            dropout=args.dropout,
            seed=args.seed,
            verbose=0 if args.quiet else 1,
        )
    except ImportError as exc:
        print(exc)
        return 1
    except ValueError as exc:
        print(exc)
        return 1

    print_report(strategy, series, result, args)

    report_df = pd.DataFrame({
        'datetime': result.split.test.index,
        'actual_equity': result.actual_equity,
        'predicted_equity': result.predicted_equity,
        'actual_pct': result.split.test.to_numpy(),
        'predicted_pct': result.predicted_returns,
        'block': [i // result.block_days + 1 for i in range(len(result.split.test))],
    })
    output_path = make_output_path(args.output, strategy.number)
    write_dataframe_csv(report_df, output_path)
    print(f'CSV: {output_path.resolve()}')

    if not args.no_show:
        plot_portfolio(strategy, result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
