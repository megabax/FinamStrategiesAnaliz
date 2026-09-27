"""CLI: LSTM-прогноз дневного % стратегии. Train — первая половина, test — следующая."""

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

from lib.csv_export import write_dataframe_csv
from lib.nnlib import (
    BATCH_SIZE,
    DROPOUT,
    EPOCHS,
    LSTM_UNITS,
    N_STEPS_AHEAD,
    RANDOM_SEED,
    TRAIN_RATIO,
    WINDOW_SIZE,
    run_lstm_forecast,
)
from lib.save import create_session
from models.strategies import History, Strategy

REPORTS_DIR = Path('reports')


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
            'LSTM-прогноз дневного %% стратегии: обучение на первой половине истории, '
            'проверка качества на второй (следующий по времени интервал)'
        ),
    )
    parser.add_argument(
        '-n', '--number',
        type=int,
        required=True,
        help='Номер стратегии (поле number на comon.ru)',
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
        default=WINDOW_SIZE,
        help=f'Длина look-back окна LSTM (по умолчанию {WINDOW_SIZE})',
    )
    parser.add_argument(
        '--horizon',
        type=int,
        default=N_STEPS_AHEAD,
        help='Горизонт обучения в днях (оценка — 1 шаг walk-forward)',
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
        help='CSV факт/прогноз (по умолчанию reports/forecast_<number>_<дата>.csv)',
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


def load_strategy_series(session, number: int, from_date, to_date) -> tuple[Strategy, pd.Series]:
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
    df = df.dropna(subset=['perc_income_day']).sort_values('datetime')
    series = pd.Series(
        df['perc_income_day'].to_numpy(),
        index=df['datetime'],
        name='perc_income_day',
    )
    return strategy, series


def make_output_path(arg_value: str | None, number: int) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    if arg_value:
        return Path(arg_value)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return REPORTS_DIR / f'forecast_{number}_{stamp}.csv'


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
        f'{len(split.train)} дней (первая половина, сплошной интервал)',
    )
    print(
        f'Тест:     {split.test_from:%d.%m.%Y} — {split.test_to:%d.%m.%Y}, '
        f'{len(split.test)} дней (интервал сразу после обучения)',
    )
    print(
        f'Окно={args.window}, горизонт обучения={args.horizon}, '
        f'эпохи≤{args.epochs}, seed={args.seed}',
    )
    print()
    print('Качество на тесте (walk-forward, 1 шаг вперёд, окно обновляется фактом):')
    print(f'  MAE:    {fmt(m["mae"], ".4f"):<10}  наивный (вчера=сегодня): {fmt(m["mae_naive"], ".4f")}')
    print(f'  RMSE:   {fmt(m["rmse"], ".4f"):<10}  наивный: {fmt(m["rmse_naive"], ".4f")}')
    print(
        f'  DirAcc: {fmt(m["directional_pct"], ".2f")}%{" " * 6}'
        f'наивный: {fmt(m["directional_pct_naive"], ".2f")}%',
    )
    print(f'  Corr:   {fmt(m["corr"], ".4f")}')
    if m['mae'] < m['mae_naive']:
        print('LSTM точнее наивного прогноза по MAE.')
    elif m['mae'] > m['mae_naive']:
        print('Наивный прогноз точнее LSTM по MAE.')
    else:
        print('MAE LSTM и наивного прогноза совпадают.')


def plot_forecast(strategy: Strategy, series: pd.Series, result) -> None:
    split = result.split
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=False)

    axes[0].plot(series.index, series.to_numpy(), color='steelblue', linewidth=1, label='Дневной %')
    axes[0].axvspan(split.train_from, split.train_to, color='C0', alpha=0.08, label='Обучение')
    axes[0].axvspan(split.test_from, split.test_to, color='C1', alpha=0.08, label='Тест')
    axes[0].axvline(split.test_from, color='black', linestyle='--', linewidth=1, label='Граница сплита')
    axes[0].set_title(f'№{strategy.number} {strategy.name}: история и хронологический сплит 50/50')
    axes[0].set_ylabel('Процент дохода')
    axes[0].legend(loc='upper left')
    axes[0].grid(True)

    axes[1].plot(
        split.test.index, split.test.to_numpy(),
        color='black', linewidth=1.5, label='Факт (тест)',
    )
    axes[1].plot(
        split.test.index, result.predicted,
        color='C1', linewidth=1.5, label='LSTM (walk-forward)',
    )
    axes[1].plot(
        split.test.index, result.naive_predicted,
        color='gray', linestyle='--', alpha=0.8, label='Наивный (вчера)',
    )
    axes[1].set_title('Тест: прогноз vs факт')
    axes[1].set_xlabel('Дата')
    axes[1].set_ylabel('Процент дохода')
    axes[1].legend(loc='upper left')
    axes[1].grid(True)

    fig.tight_layout()
    plt.show()


def main() -> int:
    args = parse_args()
    if not 0.0 < args.train_ratio < 1.0:
        print('train-ratio должен быть в интервале (0, 1).')
        return 1
    if args.window < 2 or args.horizon < 1:
        print('window ≥ 2, horizon ≥ 1.')
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
        result = run_lstm_forecast(
            series,
            train_ratio=args.train_ratio,
            window_size=args.window,
            n_steps_ahead=args.horizon,
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
        'actual_pct': result.split.test.to_numpy(),
        'lstm_pct': result.predicted,
        'naive_pct': result.naive_predicted,
    })
    output_path = make_output_path(args.output, strategy.number)
    write_dataframe_csv(report_df, output_path)
    print(f'CSV: {output_path.resolve()}')

    if not args.no_show:
        plot_forecast(strategy, series, result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
