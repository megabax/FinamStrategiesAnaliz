"""График дневной доходности стратегии со скользящим средним."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import select

from lib.save import create_session
from models.strategies import History, Strategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='График дневного % дохода стратегии со скользящим средним и полосами ±std',
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
        help='Размер окна для скользящего среднего и std (по умолчанию 100)',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    window_size = args.window

    session = create_session()
    try:
        strategy = session.query(Strategy).filter(Strategy.number == args.number).first()
        if strategy is None:
            print(f'Стратегия с номером {args.number} не найдена в базе.')
            return 1

        stmt = (
            select(History.datetime, History.perc_income_day)
            .filter(History.strategy_id == strategy.id)
            .order_by(History.datetime)
        )
        df = pd.read_sql(stmt, session.bind)
    finally:
        session.close()

    if df.empty:
        print(f'Нет истории для стратегии №{strategy.number} ({strategy.name}).')
        return 1

    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    df.sort_index(inplace=True)

    df['moving_avg'] = df['perc_income_day'].rolling(window=window_size).mean()
    df['moving_std'] = df['perc_income_day'].rolling(window=window_size).std()
    df['upper_band'] = df['moving_avg'] + df['moving_std']
    df['lower_band'] = df['moving_avg'] - df['moving_std']

    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['perc_income_day'], label='Процент дохода за день', color='skyblue', alpha=0.7)
    plt.plot(
        df.index, df['moving_avg'],
        label=f'Скользящее среднее ({window_size} дней)',
        color='orange', linewidth=2,
    )
    plt.plot(
        df.index, df['upper_band'],
        label='Верхняя зона колебаний (MA + STD)',
        color='red', linestyle='--', alpha=0.6,
    )
    plt.plot(
        df.index, df['lower_band'],
        label='Нижняя зона колебаний (MA - STD)',
        color='green', linestyle='--', alpha=0.6,
    )
    plt.fill_between(df.index, df['lower_band'], df['upper_band'], color='gray', alpha=0.2)

    plt.title(
        f'№{strategy.number} {strategy.name}: дневной % дохода '
        f'(MA ± STD, окно {window_size})',
    )
    plt.xlabel('Дата')
    plt.ylabel('Процент дохода')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    print(f'Стратегия №{strategy.number}: {strategy.name}, дней={len(df)}')
    print(df.tail())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
