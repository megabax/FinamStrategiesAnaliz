"""Тесты хронологического сплита, окон и метрик LSTM-прогноза (без tensorflow)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.nnlib import (
    MinMax1D,
    anchored_block_equity,
    chronological_split,
    create_sequences,
    equity_from_returns_pct,
    evaluate_forecast,
    persistence_forecast,
    recursive_block_predict,
    walk_forward_predict,
)


def _series(n: int = 10) -> pd.Series:
    idx = pd.date_range('2024-01-01', periods=n, freq='D')
    return pd.Series(np.arange(n, dtype=float), index=idx)


def test_chronological_split_is_contiguous_halves():
    series = _series(10)
    split = chronological_split(series, train_ratio=0.5)
    assert list(split.train.to_numpy()) == [0, 1, 2, 3, 4]
    assert list(split.test.to_numpy()) == [5, 6, 7, 8, 9]
    assert split.train_to < split.test_from
    assert split.train_from == pd.Timestamp('2024-01-01')
    assert split.test_from == pd.Timestamp('2024-01-06')


def test_chronological_split_rejects_shuffle_gap():
    series = _series(4)
    with pytest.raises(ValueError):
        chronological_split(series, train_ratio=0.0)


def test_create_sequences_shapes_and_values():
    x, y = create_sequences(np.arange(10, dtype=float), window_size=3, n_steps_ahead=2)
    assert x.shape == (6, 3, 1)
    assert y.shape == (6, 2)
    np.testing.assert_array_equal(x[0].ravel(), [0, 1, 2])
    np.testing.assert_array_equal(y[0], [3, 4])
    np.testing.assert_array_equal(x[-1].ravel(), [5, 6, 7])
    np.testing.assert_array_equal(y[-1], [8, 9])


def test_scaler_fit_only_on_train():
    scaler = MinMax1D().fit([0.0, 10.0])
    np.testing.assert_allclose(scaler.transform([0.0, 5.0, 10.0]), [0.0, 0.5, 1.0])
    np.testing.assert_allclose(scaler.inverse([0.0, 0.5, 1.0]), [0.0, 5.0, 10.0])


def test_evaluate_perfect_forecast():
    metrics = evaluate_forecast([1.0, -2.0, 3.0], [1.0, -2.0, 3.0])
    assert metrics['mae'] == 0.0
    assert metrics['rmse'] == 0.0
    assert metrics['directional_pct'] == 100.0
    assert metrics['corr'] == 1.0


def test_persistence_uses_previous_actual():
    naive = persistence_forecast([1.0, 2.0], [3.0, 4.0, 5.0])
    np.testing.assert_array_equal(naive, [2.0, 3.0, 4.0])


def test_walk_forward_uses_actuals_not_predictions():
    scaler = MinMax1D().fit([0.0, 10.0])
    seen = []

    def predict_last(x: np.ndarray) -> np.ndarray:
        seen.append(x.copy())
        return np.array([[x[0, -1, 0]]])

    preds = walk_forward_predict(
        predict_last,
        scaler,
        train_values=[0.0, 10.0, 5.0],
        test_values=[2.0, 8.0],
        window_size=2,
    )
    # модель возвращает последний элемент окна в шкале 0..1, inverse → факт «вчера»
    np.testing.assert_allclose(preds, [5.0, 2.0])
    first_window = seen[0][0, :, 0]
    np.testing.assert_allclose(first_window, scaler.transform([10.0, 5.0]))
    second_window = seen[1][0, :, 0]
    np.testing.assert_allclose(second_window, scaler.transform([5.0, 2.0]))


def test_recursive_block_feeds_prediction_then_resets_to_actual():
    scaler = MinMax1D().fit([0.0, 10.0])
    seen = []

    def predict_last(x: np.ndarray) -> np.ndarray:
        seen.append(x.copy())
        return np.array([[x[0, -1, 0]]])

    preds = recursive_block_predict(
        predict_last,
        scaler,
        train_values=[0.0, 10.0, 5.0],
        test_values=[2.0, 8.0, 4.0, 6.0],
        window_size=2,
        block_days=2,
    )
    # блок 1: окно факт [10, 5] → 5, затем прогноз 5 в окне → 5
    # блок 2: сброс на факт [2, 8] → 8, затем прогноз 8 в окне → 8
    np.testing.assert_allclose(preds, [5.0, 5.0, 8.0, 8.0])
    np.testing.assert_allclose(seen[0][0, :, 0], scaler.transform([10.0, 5.0]))
    np.testing.assert_allclose(seen[1][0, :, 0], scaler.transform([5.0, 5.0]))
    np.testing.assert_allclose(seen[2][0, :, 0], scaler.transform([2.0, 8.0]))
    np.testing.assert_allclose(seen[3][0, :, 0], scaler.transform([8.0, 8.0]))


def test_equity_from_returns_compounds():
    np.testing.assert_allclose(equity_from_returns_pct([10.0, 10.0], start=1.0), [1.1, 1.21])


def test_anchored_block_equity_restarts_from_actual():
    actual_eq, pred_eq = anchored_block_equity(
        actual_returns=[10.0, 10.0, 10.0, 10.0],
        predicted_returns=[0.0, 0.0, 0.0, 0.0],
        block_days=2,
        start=1.0,
    )
    np.testing.assert_allclose(actual_eq, [1.1, 1.21, 1.331, 1.4641])
    np.testing.assert_allclose(pred_eq, [1.0, 1.0, 1.21, 1.21])
