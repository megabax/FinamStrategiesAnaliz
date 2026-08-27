"""Тесты MaStdThresholdAlgorithm и дневного PnL симулятора."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from sim.algorithm import BuyAndHoldAlgorithm, MaStdThresholdAlgorithm
from sim.context import MarketContext
from sim.strategy_sim import StrategySimulator
from sim.types import Bar, Position, PositionState, Signal


def _bars(n: int, perc: float, strategy_id: int = 1) -> list[Bar]:
    start = date(2024, 1, 1)
    return [
        Bar(dt=start + timedelta(days=i), strategy_id=strategy_id, perc_income_day=perc)
        for i in range(n)
    ]


def test_ma_std_enter_when_above_thresholds():
    algo = MaStdThresholdAlgorithm(window=5, ma_min=0.05, ratio_min=0.5)
    # постоянный +1% → MA=1, STD=0 → ratio=+inf
    history = _bars(4, 1.0)
    bar = _bars(5, 1.0)[-1]
    ctx = MarketContext(bar=bar, history=history, position=Position())
    assert algo.decide(ctx) is Signal.ENTER


def test_ma_std_hold_until_window_ready():
    algo = MaStdThresholdAlgorithm(window=5, ma_min=0.0, ratio_min=0.0)
    history = _bars(2, 1.0)
    bar = _bars(3, 1.0)[-1]
    ctx = MarketContext(bar=bar, history=history, position=Position())
    assert algo.decide(ctx) is Signal.HOLD


def test_ma_std_exit_when_ma_below():
    algo = MaStdThresholdAlgorithm(window=5, ma_min=0.5, ratio_min=0.0)
    vals = [0.0, 0.0, 0.0, 0.0, 0.0]
    start = date(2024, 1, 1)
    history = [
        Bar(dt=start + timedelta(days=i), strategy_id=1, perc_income_day=vals[i])
        for i in range(4)
    ]
    bar = Bar(dt=start + timedelta(days=4), strategy_id=1, perc_income_day=vals[4])
    pos = Position(state=PositionState.LONG, qty=1.0, entry_date=start)
    ctx = MarketContext(bar=bar, history=history, position=pos)
    assert algo.decide(ctx) is Signal.EXIT


def test_simulator_pnl_only_when_long():
    bars = _bars(3, 10.0)  # +10% в день
    sim = StrategySimulator(1, BuyAndHoldAlgorithm(), initial_cash=1.0)
    sim.run(bars)
    assert sim.equity == pytest.approx(1.1 ** 3)
    assert len(sim.equity_curve) == 3


def test_ma_std_exit_skips_day_return():
    algo = MaStdThresholdAlgorithm(window=2, ma_min=0.5, ratio_min=0.0)
    start = date(2024, 1, 1)
    bars = [
        Bar(dt=start, strategy_id=1, perc_income_day=1.0),
        Bar(dt=start + timedelta(days=1), strategy_id=1, perc_income_day=1.0),
        Bar(dt=start + timedelta(days=2), strategy_id=1, perc_income_day=-2.0),
    ]
    sim = StrategySimulator(1, algo, initial_cash=1.0)
    trades = sim.run(bars)
    assert trades[0].side is Signal.ENTER
    # day0 flat → 1; day1 enter +1% → 1.01; day2 exit до PnL → 1.01
    assert sim.equity == pytest.approx(1.01)
