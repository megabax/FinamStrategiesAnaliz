"""Алгоритмы управления входом/выходом из стратегии."""

from __future__ import annotations

import math
import statistics
from abc import ABC, abstractmethod

from sim.context import MarketContext
from sim.types import Signal, Trade


class StrategyAlgorithm(ABC):
    """Абстрактный алгоритм: решить HOLD / ENTER / EXIT на текущем шаге."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Человекочитаемое имя алгоритма."""

    @abstractmethod
    def decide(self, ctx: MarketContext) -> Signal:
        """Вернуть сигнал по контексту. Шортов быть не должно (только long-only)."""

    def on_fill(self, trade: Trade) -> None:
        """Хук после исполнения сделки (по умолчанию ничего не делает)."""


class BuyAndHoldAlgorithm(StrategyAlgorithm):
    """Войти при первой возможности и держать до конца."""

    @property
    def name(self) -> str:
        return 'buy_and_hold'

    def decide(self, ctx: MarketContext) -> Signal:
        if ctx.position.is_flat:
            return Signal.ENTER
        return Signal.HOLD


class MaStdThresholdAlgorithm(StrategyAlgorithm):
    """Вход/выход по порогам скользящего среднего дневного % и отношения MA/STD.

    Как в ``analiz/stathist``: окно ``window`` по ``perc_income_day`` (включая текущий бар).

    - ENTER, если вне позиции и ``MA >= ma_min`` и ``MA/STD >= ratio_min``;
    - EXIT, если в позиции и ``MA < ma_min`` или ``MA/STD < ratio_min``;
    - иначе HOLD (ждать следующего входа или продолжать держать).
    """

    def __init__(
        self,
        *,
        window: int = 100,
        ma_min: float = 0.0,
        ratio_min: float = 0.05,
    ) -> None:
        if window < 2:
            raise ValueError('window должен быть >= 2')
        self.window = window
        self.ma_min = float(ma_min)
        self.ratio_min = float(ratio_min)

    @property
    def name(self) -> str:
        return f'ma_std_w{self.window}_ma{self.ma_min:g}_r{self.ratio_min:g}'

    def decide(self, ctx: MarketContext) -> Signal:
        stats = self._ma_std(ctx)
        if stats is None:
            return Signal.HOLD

        ma, std = stats
        ratio = self._ratio(ma, std)
        ok = ma >= self.ma_min and ratio >= self.ratio_min

        if ctx.position.is_flat:
            return Signal.ENTER if ok else Signal.HOLD
        # LONG
        return Signal.HOLD if ok else Signal.EXIT

    def _ma_std(self, ctx: MarketContext) -> tuple[float, float] | None:
        values = [b.perc_income_day for b in ctx.history]
        values.append(ctx.bar.perc_income_day)
        if len(values) < self.window:
            return None
        window_vals = values[-self.window :]
        ma = statistics.fmean(window_vals)
        # pandas rolling().std() по умолчанию ddof=1
        std = statistics.stdev(window_vals)
        return ma, std

    @staticmethod
    def _ratio(ma: float, std: float) -> float:
        if std < 1e-12:
            if ma > 0:
                return math.inf
            if ma < 0:
                return -math.inf
            return 0.0
        return ma / std
