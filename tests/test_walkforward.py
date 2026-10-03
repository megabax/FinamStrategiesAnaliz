"""Тесты walk-forward: нет утечки будущего, знак и vol считаются по прошлым блокам."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.walkforward import (
    block_return_pct,
    collect_past_blocks,
    feature_vector,
    follow_signal_equity,
    hit_rate,
    ols_fit,
    ols_predict,
    predict_origin,
    summarize_walkforward,
    walk_forward_signal,
)


def test_block_return_compounds():
    assert block_return_pct([10.0, 10.0]) == pytest.approx(21.0)


def test_feature_vector_uses_only_passed_history():
    hist = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    feat = feature_vector(hist, lookback=3, block_days=2)
    np.testing.assert_allclose(feat[0], (3 + 4 + 5) / 3)
    np.testing.assert_allclose(feat[3], (4 + 5) / 2)


def test_collect_past_blocks_stops_before_origin():
    returns = np.arange(20, dtype=float)
    x, y, vols = collect_past_blocks(returns, origin=12, lookback=4, block_days=4)
    assert len(y) == 2
    assert y[0] == pytest.approx(block_return_pct(returns[4:8]))
    assert y[1] == pytest.approx(block_return_pct(returns[8:12]))
    np.testing.assert_allclose(x[1], feature_vector(returns[:8], 4, 4))


def test_predict_origin_does_not_see_future_block():
    returns = np.concatenate([np.ones(20), np.full(5, 50.0)])
    row = predict_origin(returns, origin=20, lookback=4, block_days=5, min_train_blocks=2)
    assert row['actual_ret'] == pytest.approx(block_return_pct(returns[20:25]))
    # линейная модель училась только на единицах — не на 50%
    assert row['n_train_blocks'] == 3
    assert row['linear_ret'] < 20


def test_ols_recovers_linear_relation():
    x = np.array([[1.0], [2.0], [3.0], [4.0]])
    y = 2.0 * x[:, 0] + 1.0
    coef = ols_fit(x, y)
    assert ols_predict(coef, [5.0]) == pytest.approx(11.0)


def test_walk_forward_is_expanding_and_contiguous():
    idx = pd.date_range('2024-01-01', periods=80, freq='D')
    series = pd.Series(np.linspace(-1, 1, 80), index=idx)
    wf = walk_forward_signal(series, block_days=5, lookback=5, min_train_blocks=3)
    assert wf['origin'].is_monotonic_increasing
    assert (wf['origin'].diff().dropna() == 5).all()
    assert wf['n_train_blocks'].iloc[-1] > wf['n_train_blocks'].iloc[0]


def test_always_up_series_ma_is_perfect():
    idx = pd.date_range('2024-01-01', periods=80, freq='D')
    series = pd.Series(np.full(80, 1.0), index=idx)
    wf = walk_forward_signal(series, block_days=5, lookback=5, min_train_blocks=3)
    assert hit_rate(wf['actual_dir'], wf['naive_ma_dir']) == 100.0
    summary = summarize_walkforward(wf)
    assert summary['blocks'] == len(wf)
    assert summary['naive_ma_dir_pct'] == 100.0


def test_follow_signal_flat_when_negative():
    idx = pd.date_range('2024-01-01', periods=10, freq='D')
    series = pd.Series(np.full(10, 10.0), index=idx)
    wf = pd.DataFrame({'origin': [2], 'linear_dir': [-1]})
    eq = follow_signal_equity(series, wf, start=1.0)
    assert eq.iloc[0] == pytest.approx(1.1)
    assert eq.iloc[1] == pytest.approx(1.21)
    assert eq.iloc[2] == pytest.approx(1.21)
