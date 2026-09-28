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
FEATURE_MA = 10
FEATURE_MOM = 5
PORTFOLIO_WINDOW = 20


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


class StandardScalerND:
    """Стандартизация признаков по train: mean/std по столбцам, без утечки из теста."""

    def __init__(self) -> None:
        self.mean = np.array([0.0])
        self.std = np.array([1.0])

    def fit(self, values: np.ndarray) -> StandardScalerND:
        arr = np.asarray(values, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        self.mean = arr.mean(axis=0)
        self.std = arr.std(axis=0)
        self.std = np.where(self.std < 1e-12, 1.0, self.std)
        return self

    def transform(self, values: np.ndarray) -> np.ndarray:
        arr = np.asarray(values, dtype=float)
        one_d = arr.ndim == 1
        if one_d:
            arr = arr.reshape(-1, 1)
        out = (arr - self.mean) / self.std
        return out.reshape(-1) if one_d else out


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
    naive_equity: np.ndarray
    block_days: int
    metrics: dict
    history: dict | None = None


@dataclass
class TrainedLstm:
    split: ChronoSplit
    scaler: MinMax1D
    predict_scaled: PredictFn
    history: dict | None


@dataclass
class TrainedBlockLstm:
    split: ChronoSplit
    feature_scaler: StandardScalerND
    predict_fn: PredictFn
    history: dict | None
    n_features: int


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


def make_return_features(
    returns: pd.Series,
    ma_window: int = FEATURE_MA,
    mom_window: int = FEATURE_MOM,
) -> pd.DataFrame:
    """Признаки только из прошлого и текущего дня: r, MA, STD, импульс. Без заглядывания вперёд."""
    r = pd.to_numeric(returns, errors='coerce').astype(float)
    df = pd.DataFrame({'r': r}, index=returns.index)
    df['ma'] = r.rolling(ma_window, min_periods=ma_window).mean()
    df['std'] = r.rolling(ma_window, min_periods=ma_window).std()
    df['mom'] = r.rolling(mom_window, min_periods=mom_window).sum()
    return df.dropna()


def create_block_sequences(
    features: np.ndarray,
    targets: np.ndarray,
    window_size: int,
    block_days: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Окно признаков → следующие block_days дневных % (цель не масштабируется)."""
    feat = np.asarray(features, dtype=float)
    tgt = np.asarray(targets, dtype=float).reshape(-1)
    if feat.ndim != 2:
        raise ValueError('features должны быть 2D (time, n_features)')
    if len(feat) != len(tgt):
        raise ValueError('features и targets разной длины')
    n = len(feat) - window_size - block_days + 1
    if n <= 0:
        raise ValueError(
            f'Недостаточно точек для блока: len={len(feat)}, window={window_size}, '
            f'block={block_days}',
        )
    x = np.empty((n, window_size, feat.shape[1]), dtype=float)
    y = np.empty((n, block_days), dtype=float)
    for i in range(n):
        x[i] = feat[i:i + window_size]
        y[i] = tgt[i + window_size:i + window_size + block_days]
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


def local_mean_block_predict(
    train_values: Sequence[float],
    test_values: Sequence[float],
    block_days: int,
    lookback: int,
) -> np.ndarray:
    """Наивный блок: все n дней = среднее факт. доходности за lookback до старта блока."""
    train_arr = np.asarray(train_values, dtype=float).reshape(-1)
    test_arr = np.asarray(test_values, dtype=float).reshape(-1)
    actuals = np.concatenate([train_arr, test_arr])
    offset = len(train_arr)
    preds = np.empty(len(test_arr), dtype=float)
    lb = max(1, lookback)
    for block_start in range(0, len(test_arr), block_days):
        block_end = min(block_start + block_days, len(test_arr))
        abs_index = offset + block_start
        seed = actuals[max(0, abs_index - lb):abs_index]
        mean_r = float(seed.mean()) if len(seed) else 0.0
        preds[block_start:block_end] = mean_r
    return preds


def direct_block_predict(
    predict_fn: PredictFn,
    feature_scaler: StandardScalerND,
    features: pd.DataFrame,
    test_index: pd.Index,
    window_size: int,
    block_days: int,
) -> np.ndarray:
    """Каждый блок: окно только из факта до старта, один прогноз на n дней (без рекурсии)."""
    preds = np.empty(len(test_index), dtype=float)
    n_features = features.shape[1]
    for block_start in range(0, len(test_index), block_days):
        block_end = min(block_start + block_days, len(test_index))
        start_date = test_index[block_start]
        hist = features.loc[features.index < start_date]
        if len(hist) < window_size:
            raise ValueError(
                f'Мало факта до {start_date.date()}: {len(hist)} < window {window_size}',
            )
        raw_x = hist.iloc[-window_size:].to_numpy(dtype=float)
        x = feature_scaler.transform(raw_x).reshape(1, window_size, n_features)
        raw = np.asarray(predict_fn(x), dtype=float).reshape(-1)
        need = block_end - block_start
        if len(raw) == 0:
            raise ValueError('Модель вернула пустой прогноз блока')
        if len(raw) < need:
            raw = np.concatenate([raw, np.full(need - len(raw), raw[-1])])
        preds[block_start:block_end] = np.clip(raw[:need], -50.0, 50.0)
    return preds


def block_direction_pct(
    actual_equity: Sequence[float],
    predicted_equity: Sequence[float],
    block_days: int,
    start: float = 1.0,
) -> float:
    actual_arr = np.asarray(actual_equity, dtype=float).reshape(-1)
    predicted_arr = np.asarray(predicted_equity, dtype=float).reshape(-1)
    hits = 0
    n_blocks = 0
    for block_start in range(0, len(actual_arr), block_days):
        end = min(block_start + block_days, len(actual_arr)) - 1
        anchor = start if block_start == 0 else float(actual_arr[block_start - 1])
        actual_move = float(actual_arr[end] - anchor)
        pred_move = float(predicted_arr[end] - anchor)
        if actual_move == 0 or np.sign(actual_move) == np.sign(pred_move):
            hits += 1
        n_blocks += 1
    return round(100.0 * hits / n_blocks, 2) if n_blocks else float('nan')


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
        from tensorflow.keras.layers import Dense, Dropout, Input, LSTM
        from tensorflow.keras.models import Sequential
    except ImportError as exc:
        raise ImportError(
            'Для прогноза нужен tensorflow. Установите: pip install tensorflow',
        ) from exc
    return Sequential, LSTM, Dense, Dropout, EarlyStopping, Input


def make_block_path_loss():
    """MAE по дням + штраф за ошибку траектории log-портфеля на горизонте блока."""
    import tensorflow as tf

    def block_path_loss(y_true, y_pred):
        y_pred_clip = tf.clip_by_value(y_pred, -50.0, 50.0)
        daily = tf.reduce_mean(tf.abs(y_true - y_pred_clip))
        log_true = tf.math.log(tf.maximum(1.0 + y_true / 100.0, 1e-4))
        log_pred = tf.math.log(tf.maximum(1.0 + y_pred_clip / 100.0, 1e-4))
        cum_true = tf.cumsum(log_true, axis=1)
        cum_pred = tf.cumsum(log_pred, axis=1)
        path = tf.reduce_mean(tf.square(cum_true - cum_pred))
        end = tf.reduce_mean(tf.square(cum_true[:, -1] - cum_pred[:, -1]))
        return daily + 10.0 * path + 20.0 * end

    return block_path_loss


def build_lstm_model(
    window_size: int = WINDOW_SIZE,
    n_steps_ahead: int = N_STEPS_AHEAD,
    units: int = LSTM_UNITS,
    dropout: float = DROPOUT,
    n_features: int = 1,
    loss='mse',
):
    Sequential, LSTM, Dense, Dropout, _, Input = _import_keras()
    model = Sequential([
        Input(shape=(window_size, n_features)),
        LSTM(units),
        Dropout(dropout),
        Dense(max(units // 2, 8), activation='tanh'),
        Dense(n_steps_ahead),
    ])
    model.compile(optimizer='adam', loss=loss)
    return model


def fit_lstm(
    model,
    x_train: np.ndarray,
    y_train: np.ndarray,
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    verbose: int = 1,
):
    _, _, _, _, EarlyStopping, _ = _import_keras()
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


def train_lstm_block_model(
    series: pd.Series,
    train_ratio: float = TRAIN_RATIO,
    window_size: int = PORTFOLIO_WINDOW,
    block_days: int = BLOCK_DAYS,
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    units: int = LSTM_UNITS,
    dropout: float = DROPOUT,
    seed: int = RANDOM_SEED,
    verbose: int = 1,
) -> tuple[TrainedBlockLstm, pd.DataFrame]:
    """LSTM: признаки (r/MA/STD/импульс) → n дневных % блока. Обучение только на 1-й половине."""
    split = chronological_split(series, train_ratio=train_ratio)
    features = make_return_features(series)
    train_feat = features.loc[features.index <= split.train_to]
    if len(train_feat) < window_size + block_days:
        raise ValueError(
            f'Первая половина слишком короткая для окна {window_size} и блока {block_days}: '
            f'{len(train_feat)} точек с признаками',
        )

    set_seed(seed)
    targets = series.reindex(train_feat.index).astype(float).to_numpy()
    scaler = StandardScalerND().fit(train_feat.to_numpy())
    x_raw, y_train = create_block_sequences(
        train_feat.to_numpy(),
        targets,
        window_size=window_size,
        block_days=block_days,
    )
    x_train = np.empty_like(x_raw)
    for i in range(len(x_raw)):
        x_train[i] = scaler.transform(x_raw[i])

    n_features = train_feat.shape[1]
    model = build_lstm_model(
        window_size=window_size,
        n_steps_ahead=block_days,
        units=units,
        dropout=dropout,
        n_features=n_features,
        loss=make_block_path_loss(),
    )
    history = fit_lstm(
        model,
        x_train,
        y_train,
        epochs=epochs,
        batch_size=batch_size,
        verbose=verbose,
    )

    def predict_fn(x: np.ndarray) -> np.ndarray:
        return model.predict(x, verbose=0)

    trained = TrainedBlockLstm(
        split=split,
        feature_scaler=scaler,
        predict_fn=predict_fn,
        history=history.history if history is not None else None,
        n_features=n_features,
    )
    return trained, features


def run_lstm_portfolio_forecast(
    series: pd.Series,
    train_ratio: float = TRAIN_RATIO,
    window_size: int = PORTFOLIO_WINDOW,
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
    """Обучает на 1-й половине; на 2-й каждый блок n дней предсказывается целиком с факта."""
    del n_steps_ahead  # горизонт = длина блока, одношаговая рекурсия по дневному % давала константный наклон
    trained, features = train_lstm_block_model(
        series,
        train_ratio=train_ratio,
        window_size=window_size,
        block_days=block_days,
        epochs=epochs,
        batch_size=batch_size,
        units=units,
        dropout=dropout,
        seed=seed,
        verbose=verbose,
    )
    split = trained.split
    predicted_returns = direct_block_predict(
        trained.predict_fn,
        trained.feature_scaler,
        features,
        split.test.index,
        window_size=window_size,
        block_days=block_days,
    )
    naive_returns = local_mean_block_predict(
        split.train.to_numpy(),
        split.test.to_numpy(),
        block_days=block_days,
        lookback=window_size,
    )
    actual_equity, predicted_equity = anchored_block_equity(
        split.test.to_numpy(),
        predicted_returns,
        block_days=block_days,
        start=start_equity,
    )
    _, naive_equity = anchored_block_equity(
        split.test.to_numpy(),
        naive_returns,
        block_days=block_days,
        start=start_equity,
    )
    metrics = evaluate_equity(actual_equity, predicted_equity)
    naive_metrics = evaluate_equity(actual_equity, naive_equity)
    metrics['blocks'] = int(np.ceil(len(split.test) / block_days))
    metrics['block_dir_pct'] = block_direction_pct(
        actual_equity, predicted_equity, block_days, start=start_equity,
    )
    metrics['block_dir_pct_naive'] = block_direction_pct(
        actual_equity, naive_equity, block_days, start=start_equity,
    )
    metrics['mae_naive'] = naive_metrics['mae']
    return PortfolioForecastResult(
        split=split,
        predicted_returns=predicted_returns,
        actual_equity=actual_equity,
        predicted_equity=predicted_equity,
        naive_equity=naive_equity,
        block_days=block_days,
        metrics=metrics,
        history=trained.history,
    )
