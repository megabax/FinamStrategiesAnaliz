"""LSTM-прогноз дневной доходности: хронологический сплит, обучение, walk-forward."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
import pandas as pd

WINDOW_SIZE = 10
N_STEPS_AHEAD = 1
TRAIN_RATIO = 0.5
EPOCHS = 50
BATCH_SIZE = 32
LSTM_UNITS = 32
DROPOUT = 0.2
RANDOM_SEED = 42
BLOCK_DAYS = 5


class MinMax1D:
    """Min-max только по train, чтобы не было утечки из теста."""

    def __init__(self) -> None:
        self.min = 0.0
        self.span = 1.0

    def fit(self, values: Sequence[float]) -> MinMax1D:
        arr = np.asarray(values, dtype=float).reshape(-1)
        self.min = float(arr.min()) if len(arr) else 0.0
        vmax = float(arr.max()) if len(arr) else 1.0
        self.span = vmax - self.min if vmax != self.min else 1.0
        return self

    def transform(self, values: Sequence[float]) -> np.ndarray:
        arr = np.asarray(values, dtype=float).reshape(-1)
        return (arr - self.min) / self.span

    def inverse(self, values: Sequence[float]) -> np.ndarray:
        arr = np.asarray(values, dtype=float).reshape(-1)
        return arr * self.span + self.min


@dataclass(frozen=True)
class ChronoSplit:
    train: pd.Series
    test: pd.Series

    @property
    def train_from(self):
        return self.train.index.min()

    @property
    def train_to(self):
        return self.train.index.max()

    @property
    def test_from(self):
        return self.test.index.min()

    @property
    def test_to(self):
        return self.test.index.max()


PredictFn = Callable[[np.ndarray], np.ndarray]


@dataclass
class ForecastResult:
    split: ChronoSplit
    predicted: np.ndarray
    naive_predicted: np.ndarray
    metrics: dict
    history: dict | None = None


@dataclass
class PortfolioForecastResult:
    split: ChronoSplit
    predicted_returns: np.ndarray
    actual_equity: np.ndarray
    predicted_equity: np.ndarray
    block_days: int
    metrics: dict
    history: dict | None = None


@dataclass
class TrainedLstm:
    split: ChronoSplit
    scaler: MinMax1D
    predict_scaled: PredictFn
    history: dict | None


def chronological_split(series: pd.Series, train_ratio: float = TRAIN_RATIO) -> ChronoSplit:
    """Первая доля ряда — train, сразу за ней непрерывный test. Без перемешивания."""
    if not 0.0 < train_ratio < 1.0:
        raise ValueError(f'train_ratio должен быть в (0, 1), получено {train_ratio}')
    clean = series.dropna().sort_index()
    if len(clean) < 4:
        raise ValueError(f'Слишком короткий ряд для сплита: {len(clean)} точек')

    cut = int(len(clean) * train_ratio)
    if cut < 1 or cut >= len(clean):
        raise ValueError('После сплита одна из половин пустая')

    train = clean.iloc[:cut]
    test = clean.iloc[cut:]
    if train.index.max() >= test.index.min():
        raise ValueError('Сплит должен быть строго хронологическим')
    return ChronoSplit(train=train, test=test)


def create_sequences(
    values: Sequence[float],
    window_size: int = WINDOW_SIZE,
    n_steps_ahead: int = N_STEPS_AHEAD,
) -> tuple[np.ndarray, np.ndarray]:
    """Окна (window, 1) → следующие n_steps_ahead значений. Только по переданному отрезку."""
    arr = np.asarray(values, dtype=float).reshape(-1)
    n = len(arr) - window_size - n_steps_ahead + 1
    if n <= 0:
        raise ValueError(
            f'Недостаточно точек для окон: len={len(arr)}, window={window_size}, '
            f'horizon={n_steps_ahead}',
        )

    x = np.empty((n, window_size, 1), dtype=float)
    y = np.empty((n, n_steps_ahead), dtype=float)
    for i in range(n):
        x[i, :, 0] = arr[i:i + window_size]
        y[i] = arr[i + window_size:i + window_size + n_steps_ahead]
    return x, y


def evaluate_forecast(actual: Sequence[float], predicted: Sequence[float]) -> dict:
    actual_arr = np.asarray(actual, dtype=float).reshape(-1)
    predicted_arr = np.asarray(predicted, dtype=float).reshape(-1)
    if len(actual_arr) != len(predicted_arr):
        raise ValueError('actual и predicted разной длины')
    if len(actual_arr) == 0:
        raise ValueError('пустой ряд для оценки')

    err = predicted_arr - actual_arr
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    signs_ok = np.sign(predicted_arr) == np.sign(actual_arr)
    directional = float(signs_ok.mean() * 100.0)
    if len(actual_arr) > 1 and actual_arr.std() > 0 and predicted_arr.std() > 0:
        corr = float(np.corrcoef(actual_arr, predicted_arr)[0, 1])
    else:
        corr = float('nan')

    return {
        'n': int(len(actual_arr)),
        'mae': round(mae, 4),
        'rmse': round(rmse, 4),
        'directional_pct': round(directional, 2),
        'corr': round(corr, 4) if not np.isnan(corr) else None,
    }


def persistence_forecast(train_values: Sequence[float], test_values: Sequence[float]) -> np.ndarray:
    """Наивный прогноз: завтра = фактический вчера (последний train, затем факт теста)."""
    train_arr = np.asarray(train_values, dtype=float).reshape(-1)
    test_arr = np.asarray(test_values, dtype=float).reshape(-1)
    if len(train_arr) == 0 or len(test_arr) == 0:
        raise ValueError('Для наивного прогноза нужны train и test')
    prev = np.concatenate([train_arr[-1:], test_arr[:-1]])
    return prev


def walk_forward_predict(
    predict_scaled: PredictFn,
    scaler: MinMax1D,
    train_values: Sequence[float],
    test_values: Sequence[float],
    window_size: int = WINDOW_SIZE,
) -> np.ndarray:
    """1-шаговый walk-forward: в окно после шага кладётся факт, не прогноз."""
    train_arr = np.asarray(train_values, dtype=float).reshape(-1)
    test_arr = np.asarray(test_values, dtype=float).reshape(-1)
    if len(train_arr) < window_size:
        raise ValueError(f'В train меньше окна: {len(train_arr)} < {window_size}')
    if len(test_arr) == 0:
        raise ValueError('Пустой test')

    window = list(scaler.transform(train_arr[-window_size:]))
    preds = []
    for actual in test_arr:
        x = np.asarray(window, dtype=float).reshape(1, window_size, 1)
        y_scaled = float(np.asarray(predict_scaled(x)).reshape(-1)[0])
        preds.append(float(scaler.inverse(np.array([y_scaled]))[0]))
        window.append(float(scaler.transform(np.array([actual]))[0]))
        window.pop(0)
    return np.asarray(preds, dtype=float)


def _predict_one_return(
    predict_scaled: PredictFn,
    scaler: MinMax1D,
    window_scaled: list[float],
    window_size: int,
) -> float:
    x = np.asarray(window_scaled, dtype=float).reshape(1, window_size, 1)
    y_scaled = float(np.asarray(predict_scaled(x)).reshape(-1)[0])
    return float(scaler.inverse(np.array([y_scaled]))[0])


def recursive_block_predict(
    predict_scaled: PredictFn,
    scaler: MinMax1D,
    train_values: Sequence[float],
    test_values: Sequence[float],
    window_size: int = WINDOW_SIZE,
    block_days: int = BLOCK_DAYS,
) -> np.ndarray:
    """Рекурсивный прогноз блоками: n дней прогноз→вход, затем окно сбрасывается на факт."""
    if block_days < 1:
        raise ValueError(f'block_days должен быть ≥ 1, получено {block_days}')

    train_arr = np.asarray(train_values, dtype=float).reshape(-1)
    test_arr = np.asarray(test_values, dtype=float).reshape(-1)
    if len(train_arr) < window_size:
        raise ValueError(f'В train меньше окна: {len(train_arr)} < {window_size}')
    if len(test_arr) == 0:
        raise ValueError('Пустой test')

    actuals = np.concatenate([train_arr, test_arr])
    test_offset = len(train_arr)
    preds = np.empty(len(test_arr), dtype=float)

    for block_start in range(0, len(test_arr), block_days):
        block_end = min(block_start + block_days, len(test_arr))
        abs_index = test_offset + block_start
        seed = actuals[abs_index - window_size:abs_index]
        window = list(scaler.transform(seed))

        for k in range(block_start, block_end):
            predicted = _predict_one_return(predict_scaled, scaler, window, window_size)
            preds[k] = predicted
            window.append(float(scaler.transform(np.array([predicted]))[0]))
            window.pop(0)

    return preds


def equity_from_returns_pct(returns_pct: Sequence[float], start: float = 1.0) -> np.ndarray:
    """Состояние портфеля после каждого дня: start * cumprod(1 + r/100)."""
    r = np.asarray(returns_pct, dtype=float).reshape(-1) / 100.0
    if len(r) == 0:
        return np.array([], dtype=float)
    return start * np.cumprod(1.0 + r)


def anchored_block_equity(
    actual_returns: Sequence[float],
    predicted_returns: Sequence[float],
    block_days: int,
    start: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Факт — сплошной equity; прогноз — от фактического портфеля на старте каждого блока."""
    actual_arr = np.asarray(actual_returns, dtype=float).reshape(-1)
    predicted_arr = np.asarray(predicted_returns, dtype=float).reshape(-1)
    if len(actual_arr) != len(predicted_arr):
        raise ValueError('actual и predicted returns разной длины')
    if block_days < 1:
        raise ValueError(f'block_days должен быть ≥ 1, получено {block_days}')

    actual_equity = equity_from_returns_pct(actual_arr, start=start)
    predicted_equity = np.empty_like(actual_equity)
    for block_start in range(0, len(actual_arr), block_days):
        block_end = min(block_start + block_days, len(actual_arr))
        anchor = start if block_start == 0 else float(actual_equity[block_start - 1])
        predicted_equity[block_start:block_end] = equity_from_returns_pct(
            predicted_arr[block_start:block_end],
            start=anchor,
        )
    return actual_equity, predicted_equity


def set_seed(seed: int = RANDOM_SEED) -> None:
    np.random.seed(seed)
    try:
        import tensorflow as tf
    except ImportError:
        return
    tf.random.set_seed(seed)


def _import_keras():
    try:
        from tensorflow.keras.callbacks import EarlyStopping
        from tensorflow.keras.layers import Dense, Dropout, LSTM
        from tensorflow.keras.models import Sequential
    except ImportError as exc:
        raise ImportError(
            'Для прогноза нужен tensorflow. Установите: pip install tensorflow',
        ) from exc
    return Sequential, LSTM, Dense, Dropout, EarlyStopping


def build_lstm_model(
    window_size: int = WINDOW_SIZE,
    n_steps_ahead: int = N_STEPS_AHEAD,
    units: int = LSTM_UNITS,
    dropout: float = DROPOUT,
):
    Sequential, LSTM, Dense, Dropout, _ = _import_keras()
    model = Sequential([
        LSTM(units, input_shape=(window_size, 1)),
        Dropout(dropout),
        Dense(max(units // 2, 8), activation='relu'),
        Dense(n_steps_ahead),
    ])
    model.compile(optimizer='adam', loss='mse')
    return model


def fit_lstm(
    model,
    x_train: np.ndarray,
    y_train: np.ndarray,
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    verbose: int = 1,
):
    _, _, _, _, EarlyStopping = _import_keras()
    callbacks = []
    validation_split = 0.15 if len(x_train) >= 20 else 0.0
    if validation_split:
        callbacks.append(
            EarlyStopping(monitor='val_loss', patience=8, restore_best_weights=True),
        )
    history = model.fit(
        x_train,
        y_train,
        epochs=epochs,
        batch_size=min(batch_size, len(x_train)),
        shuffle=False,
        validation_split=validation_split,
        callbacks=callbacks,
        verbose=verbose,
    )
    return history


def train_lstm_on_series(
    series: pd.Series,
    train_ratio: float = TRAIN_RATIO,
    window_size: int = WINDOW_SIZE,
    n_steps_ahead: int = N_STEPS_AHEAD,
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    units: int = LSTM_UNITS,
    dropout: float = DROPOUT,
    seed: int = RANDOM_SEED,
    verbose: int = 1,
) -> TrainedLstm:
    """Обучает LSTM только на первой половине ряда."""
    split = chronological_split(series, train_ratio=train_ratio)
    if len(split.train) < window_size + n_steps_ahead:
        raise ValueError(
            f'Первая половина слишком короткая для окна {window_size} '
            f'и горизонта {n_steps_ahead}: {len(split.train)} точек',
        )

    set_seed(seed)
    scaler = MinMax1D().fit(split.train.to_numpy())
    train_scaled = scaler.transform(split.train.to_numpy())
    x_train, y_train = create_sequences(train_scaled, window_size, n_steps_ahead)

    model = build_lstm_model(
        window_size=window_size,
        n_steps_ahead=n_steps_ahead,
        units=units,
        dropout=dropout,
    )
    history = fit_lstm(
        model,
        x_train,
        y_train,
        epochs=epochs,
        batch_size=batch_size,
        verbose=verbose,
    )

    def predict_scaled(x: np.ndarray) -> np.ndarray:
        return model.predict(x, verbose=0)

    return TrainedLstm(
        split=split,
        scaler=scaler,
        predict_scaled=predict_scaled,
        history=history.history if history is not None else None,
    )


def run_lstm_forecast(
    series: pd.Series,
    train_ratio: float = TRAIN_RATIO,
    window_size: int = WINDOW_SIZE,
    n_steps_ahead: int = N_STEPS_AHEAD,
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    units: int = LSTM_UNITS,
    dropout: float = DROPOUT,
    seed: int = RANDOM_SEED,
    verbose: int = 1,
) -> ForecastResult:
    """Обучает LSTM на первой половине ряда и оценивает на второй (walk-forward)."""
    trained = train_lstm_on_series(
        series,
        train_ratio=train_ratio,
        window_size=window_size,
        n_steps_ahead=n_steps_ahead,
        epochs=epochs,
        batch_size=batch_size,
        units=units,
        dropout=dropout,
        seed=seed,
        verbose=verbose,
    )
    split = trained.split
    predicted = walk_forward_predict(
        trained.predict_scaled,
        trained.scaler,
        split.train.to_numpy(),
        split.test.to_numpy(),
        window_size=window_size,
    )
    naive = persistence_forecast(split.train.to_numpy(), split.test.to_numpy())
    metrics = evaluate_forecast(split.test.to_numpy(), predicted)
    naive_metrics = evaluate_forecast(split.test.to_numpy(), naive)
    metrics['mae_naive'] = naive_metrics['mae']
    metrics['rmse_naive'] = naive_metrics['rmse']
    metrics['directional_pct_naive'] = naive_metrics['directional_pct']

    return ForecastResult(
        split=split,
        predicted=predicted,
        naive_predicted=naive,
        metrics=metrics,
        history=trained.history,
    )


def evaluate_equity(actual_equity: Sequence[float], predicted_equity: Sequence[float]) -> dict:
    actual_arr = np.asarray(actual_equity, dtype=float).reshape(-1)
    predicted_arr = np.asarray(predicted_equity, dtype=float).reshape(-1)
    point = evaluate_forecast(actual_arr, predicted_arr)
    if actual_arr[0] == 0:
        end_err_pct = None
    else:
        end_err_pct = round(float((predicted_arr[-1] / actual_arr[-1] - 1.0) * 100.0), 3)
    point['end_error_pct'] = end_err_pct
    point['actual_end'] = round(float(actual_arr[-1]), 6)
    point['predicted_end'] = round(float(predicted_arr[-1]), 6)
    return point


def run_lstm_portfolio_forecast(
    series: pd.Series,
    train_ratio: float = TRAIN_RATIO,
    window_size: int = WINDOW_SIZE,
    n_steps_ahead: int = N_STEPS_AHEAD,
    block_days: int = BLOCK_DAYS,
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    units: int = LSTM_UNITS,
    dropout: float = DROPOUT,
    seed: int = RANDOM_SEED,
    verbose: int = 1,
    start_equity: float = 1.0,
) -> PortfolioForecastResult:
    """Обучает на 1-й половине, на 2-й — рекурсивные блоки по n дней → состояние портфеля."""
    trained = train_lstm_on_series(
        series,
        train_ratio=train_ratio,
        window_size=window_size,
        n_steps_ahead=n_steps_ahead,
        epochs=epochs,
        batch_size=batch_size,
        units=units,
        dropout=dropout,
        seed=seed,
        verbose=verbose,
    )
    split = trained.split
    predicted_returns = recursive_block_predict(
        trained.predict_scaled,
        trained.scaler,
        split.train.to_numpy(),
        split.test.to_numpy(),
        window_size=window_size,
        block_days=block_days,
    )
    actual_equity, predicted_equity = anchored_block_equity(
        split.test.to_numpy(),
        predicted_returns,
        block_days=block_days,
        start=start_equity,
    )
    metrics = evaluate_equity(actual_equity, predicted_equity)
    metrics['blocks'] = int(np.ceil(len(split.test) / block_days))
    return PortfolioForecastResult(
        split=split,
        predicted_returns=predicted_returns,
        actual_equity=actual_equity,
        predicted_equity=predicted_equity,
        block_days=block_days,
        metrics=metrics,
        history=trained.history,
    )
