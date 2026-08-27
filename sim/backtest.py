"""CLI: бэктест MaStdThreshold vs Buy&Hold с графиком equity."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt

from lib.save import create_session
from sim.algorithm import BuyAndHoldAlgorithm, MaStdThresholdAlgorithm
from sim.data import load_strategy_and_bars_by_number
from sim.strategy_sim import StrategySimulator
from sim.types import Signal


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
            'Симуляция входов/выходов: MA и MA/STD пороги vs buy&hold. '
            'В конце — график equity.'
        ),
    )
    parser.add_argument(
        '-n', '--number',
        type=int,
        required=True,
        help='Номер стратегии (поле number на comon.ru)',
    )
    parser.add_argument(
        '-w', '--window',
        type=int,
        default=100,
        help='Окно MA/STD (как в stathist), по умолчанию 100',
    )
    parser.add_argument(
        '--ma-min',
        type=float,
        default=0.0,
        help='Минимальное скользящее среднее дневного %% для удержания/входа',
    )
    parser.add_argument(
        '--ratio-min',
        type=float,
        default=0.05,
        help='Минимальное отношение MA/STD для удержания/входа',
    )
    parser.add_argument(
        '--from-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Начало периода (ГГГГ-ММ-ДД)',
    )
    parser.add_argument(
        '--to-date',
        type=parse_date_arg,
        default=None,
        metavar='ДАТА',
        help='Конец периода (ГГГГ-ММ-ДД)',
    )
    parser.add_argument(
        '--initial-cash',
        type=float,
        default=1.0,
        help='Начальный капитал (по умолчанию 1.0)',
    )
    parser.add_argument(
        '--no-show',
        action='store_true',
        help='Не открывать окно matplotlib (только печать итогов)',
    )
    return parser.parse_args()


def _print_summary(title: str, sim: StrategySimulator) -> None:
    enters = sum(1 for t in sim.trades if t.side is Signal.ENTER)
    exits = sum(1 for t in sim.trades if t.side is Signal.EXIT)
    ret_pct = (sim.equity / sim.initial_cash - 1.0) * 100.0
    print(
        f'{title}: equity={sim.equity:.6f} '
        f'(доход {ret_pct:+.2f}%), сделок enter/exit={enters}/{exits}, '
        f'позиция={sim.position.state.name}',
    )


def main() -> int:
    args = parse_args()

    session = create_session()
    try:
        strategy, bars = load_strategy_and_bars_by_number(
            session,
            args.number,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    finally:
        session.close()

    if not bars:
        print(f'Нет истории для стратегии №{args.number}.')
        return 1

    algo = MaStdThresholdAlgorithm(
        window=args.window,
        ma_min=args.ma_min,
        ratio_min=args.ratio_min,
    )
    sim_algo = StrategySimulator(
        strategy.id,
        algo,
        initial_cash=args.initial_cash,
    )
    sim_bh = StrategySimulator(
        strategy.id,
        BuyAndHoldAlgorithm(),
        initial_cash=args.initial_cash,
    )

    sim_algo.run(bars)
    sim_bh.run(bars)

    print(
        f'№{strategy.number} {strategy.name}: дней={len(bars)}, '
        f'{bars[0].dt} … {bars[-1].dt}',
    )
    print(f'Алгоритм: {algo.name} (window={args.window}, ma_min={args.ma_min}, ratio_min={args.ratio_min})')
    _print_summary('MA/STD', sim_algo)
    _print_summary('Buy&Hold', sim_bh)

    if args.no_show:
        return 0

    dates_a = [d for d, _ in sim_algo.equity_curve]
    eq_a = [e for _, e in sim_algo.equity_curve]
    dates_b = [d for d, _ in sim_bh.equity_curve]
    eq_b = [e for _, e in sim_bh.equity_curve]

    plt.figure(figsize=(14, 8))
    plt.plot(dates_a, eq_a, label=f'MA/STD ({algo.name})', color='C0', linewidth=2)
    plt.plot(dates_b, eq_b, label='Buy & Hold', color='C1', linewidth=2, alpha=0.85)

    enter_dates = [t.dt for t in sim_algo.trades if t.side is Signal.ENTER]
    exit_dates = [t.dt for t in sim_algo.trades if t.side is Signal.EXIT]
    eq_by_date = dict(sim_algo.equity_curve)
    if enter_dates:
        plt.scatter(
            enter_dates,
            [eq_by_date[d] for d in enter_dates],
            marker='^',
            color='green',
            s=60,
            zorder=5,
            label='Вход',
        )
    if exit_dates:
        plt.scatter(
            exit_dates,
            [eq_by_date[d] for d in exit_dates],
            marker='v',
            color='red',
            s=60,
            zorder=5,
            label='Выход',
        )

    plt.title(
        f'№{strategy.number} {strategy.name}: equity MA/STD vs Buy&Hold '
        f'(окно {args.window})',
    )
    plt.xlabel('Дата')
    plt.ylabel('Капитал')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
