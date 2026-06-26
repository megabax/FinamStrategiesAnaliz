import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from sklearn.model_selection import train_test_split # Though not for time series, useful for general split concept

# --- Parameters ---
TARGET_COLUMN = 'value'
EXCLUDE_FEATURES = ['id', 'timestamp'] # columns not to be used as input features
WINDOW_SIZE = 10 # look-back window size
N_STEPS_AHEAD = 3 # number of future steps to predict
TEST_SPLIT_RATIO = 0.2 # proportion of data for testing/validation
EPOCHS = 50
BATCH_SIZE = 32


def create_sequences(data, target_col, window_size, n_steps_ahead):
    X, y = [], []
    # Assuming data is already scaled
    for i in range(len(data) - window_size - n_steps_ahead + 1):
        # Input window: includes past values of target and features
        input_window = data[i:(i + window_size)]
        # Output window: future values of the target
        output_window = data[target_col][(i + window_size):(i + window_size + n_steps_ahead)]

        X.append(input_window)
        y.append(output_window)
    return np.array(X), np.array(y)