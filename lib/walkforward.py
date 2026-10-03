"""Walk-forward: знак и волатильность за n дней. Без LSTM и без сплита 50/50."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

BLOCK_DAYS = 10
LOOKBACK = 20
MIN_TRAIN_BLOCKS = 8

METHODS = ('linear', 'naive_ma', 'naive_last', 'naive_mean')


def block_return_pct(returns_pct: np.ndarray) -> float:
    """Итоговый % блока: 100 * (prod(1+r/100) - 1)."""
    r = np.asarray(returns_pct, dtype=float).reshape(-1) / 100.0
    if len(r) == 0:
        return 0.0
    return float((np.prod(1.0 + r) - 1.0) * 100.0)


def block_vol_pct(returns_pct: np.ndarray) -> float:
    r = np.asarray(returns_pct, dtype=float).reshape(-1)
    if len(r) < 2:
        return 0.0
    return float(r.std(ddof=1))


def feature_vector(history: np.ndarray, lookback: int, block_days: int) -> np.ndarray:
    """Признаки только из history (данные строго до прогноза)."""
    hist = np.asarray(history, dtype=float).reshape(-1)
    if len(hist) < 2:
        raise ValueError('Для признаков нужно ≥ 2 дней истории')
    window = hist[-lookback:] if len(hist) >= lookback else hist
    last_block = hist[-block_days:] if len(hist) >= block_days else hist
    mom = window[-min(5, len(window)):]
    return np.array([
        float(window.mean()),
        float(window.std(ddof=1)) if len(window) > 1 else 0.0,
        float(mom.sum()),
        float(last_block.mean()),
    ], dtype=float)


def ols_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float).reshape(-1)
    if x.ndim != 2 or len(x) != len(y) or len(y) == 0:
        raise ValueError('OLS: неверные размерности')
    design = np.column_stack([np.ones(len(x)), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return coef


def ols_predict(coef: np.ndarray, features: np.ndarray) -> float:
    feat = np.asarray(features, dtype=float).reshape(-1)
    return float(coef[0] + coef[1:] @ feat)


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def collect_past_blocks(
    returns: np.ndarray,
    origin: int,
    lookback: int,
    block_days: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Завершённые блоки строго до origin: признаки, доходность блока, vol блока."""
    xs, ys, vols = [], [], []
    start = lookback
    while start + block_days <= origin:
        xs.append(feature_vector(returns[:start], lookback, block_days))
        block = returns[start:start + block_days]
        ys.append(block_return_pct(block))
        vols.append(block_vol_pct(block))
        start += block_days
    if not xs:
        return np.empty((0, 4)), np.empty(0), np.empty(0)
    return np.vstack(xs), np.asarray(ys, dtype=float), np.asarray(vols, dtype=float)


def predict_origin(
    returns: np.ndarray,
    origin: int,
    lookback: int,
    block_days: int,
    min_train_blocks: int = MIN_TRAIN_BLOCKS,
) -> dict:
    """Прогноз на блок [origin, origin+block). Обучение только на прошлых блоках."""
    hist = returns[:origin]
    feats = feature_vector(hist, lookback, block_days)
    actual_block = returns[origin:origin + block_days]
    actual_ret = block_return_pct(actual_block)
    actual_vol = block_vol_pct(actual_block)
    actual_dir = _sign(actual_ret)

    x_past, y_past, vol_past = collect_past_blocks(returns, origin, lookback, block_days)
    naive_ma = _sign(feats[0])
    naive_last = _sign(feats[3])
    naive_mean = _sign(float(hist.mean()))

    linear_ret = float('nan')
    linear_dir = naive_ma
    if len(y_past) >= min_train_blocks:
        coef = ols_fit(x_past, y_past)
        linear_ret = ols_predict(coef, feats)
        linear_dir = _sign(linear_ret)

    pred_vol = float(feats[1])
    if len(vol_past):
        pred_vol = float(0.5 * feats[1] + 0.5 * vol_past.mean())

    return {
        'origin': origin,
        'actual_ret': actual_ret,
        'actual_vol': actual_vol,
        'actual_dir': actual_dir,
        'linear_ret': linear_ret,
        'linear_dir': linear_dir,
        'naive_ma_dir': naive_ma,
        'naive_last_dir': naive_last,
        'naive_mean_dir': naive_mean,
        'pred_vol': pred_vol,
        'n_train_blocks': int(len(y_past)),
    }


def walk_forward_signal(
    series: pd.Series,
    block_days: int = BLOCK_DAYS,
    lookback: int = LOOKBACK,
    min_train_blocks: int = MIN_TRAIN_BLOCKS,
) -> pd.DataFrame:
    """Расширяющееся окно: каждый следующий блок — новый тест, прошлые блоки — train."""
    if block_days < 1 or lookback < 2:
        raise ValueError('block_days ≥ 1, lookback ≥ 2')
    clean = series.dropna().sort_index()
    values = clean.to_numpy(dtype=float)
    index = clean.index
    first_origin = lookback + min_train_blocks * block_days
    if first_origin + block_days > len(values):
        raise ValueError(
            f'Мало истории для walk-forward: {len(values)} дней, нужно больше '
            f'{first_origin + block_days} (lookback={lookback}, '
            f'min_train_blocks={min_train_blocks}, block={block_days})',
        )

    rows = []
    origin = first_origin
    while origin + block_days <= len(values):
        row = predict_origin(values, origin, lookback, block_days, min_train_blocks)
        end = origin + block_days - 1
        row['from'] = index[origin]
        row['to'] = index[end]
        rows.append(row)
        origin += block_days
    return pd.DataFrame(rows)


def hit_rate(actual_dir: np.ndarray, pred_dir: np.ndarray) -> float:
    actual = np.asarray(actual_dir)
    pred = np.asarray(pred_dir)
    mask = actual != 0
    if not mask.any():
        return float('nan')
    return float((actual[mask] == pred[mask]).mean() * 100.0)


def vol_mae(actual_vol: np.ndarray, pred_vol: np.ndarray) -> float:
    err = np.asarray(pred_vol, dtype=float) - np.asarray(actual_vol, dtype=float)
    return float(np.mean(np.abs(err)))


def summarize_walkforward(df: pd.DataFrame) -> dict:
    if df.empty:
        raise ValueError('Пустой walk-forward')
    naive_vol = np.full(len(df), float(df['actual_vol'].mean()))
    return {
        'blocks': int(len(df)),
        'linear_dir_pct': round(hit_rate(df['actual_dir'], df['linear_dir']), 2),
        'naive_ma_dir_pct': round(hit_rate(df['actual_dir'], df['naive_ma_dir']), 2),
        'naive_last_dir_pct': round(hit_rate(df['actual_dir'], df['naive_last_dir']), 2),
        'naive_mean_dir_pct': round(hit_rate(df['actual_dir'], df['naive_mean_dir']), 2),
        'vol_mae': round(vol_mae(df['actual_vol'], df['pred_vol']), 4),
        'vol_mae_mean': round(vol_mae(df['actual_vol'], naive_vol), 4),
        'period_from': df['from'].min(),
        'period_to': df['to'].max(),
    }


def follow_signal_equity(
    series: pd.Series,
    wf: pd.DataFrame,
    signal_col: str = 'linear_dir',
    start: float = 1.0,
) -> pd.Series:
    """OOS: в блоке лонг, если сигнал > 0, иначе кэш. До walk-forward — как есть."""
    clean = series.dropna().sort_index()
    r = clean.to_numpy(dtype=float) / 100.0
    equity = np.empty(len(clean), dtype=float)
    eq = start
    origins = {
        int(row.origin): int(getattr(row, signal_col))
        for row in wf.itertuples(index=False)
    }
    origin_set = set(origins)
    current_signal = 1
    for i, ret in enumerate(r):
        if i in origin_set:
            current_signal = origins[i]
        if current_signal > 0:
            eq *= 1.0 + ret
        equity[i] = eq
    return pd.Series(equity, index=clean.index, name='signal_equity')


def equity_from_returns(series: pd.Series, start: float = 1.0) -> pd.Series:
    r = series.dropna().sort_index().astype(float) / 100.0
    return pd.Series(start * np.cumprod(1.0 + r.to_numpy()), index=r.index, name='equity')
