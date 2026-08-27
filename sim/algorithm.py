"""Алгоритмы управления входом/выходом из стратегии."""

from __future__ import annotations

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
    """Заглушка: войти при первой возможности и держать.

    Не полноценный бэктест — пример наследника ABC.
    """

    @property
    def name(self) -> str:
        return 'buy_and_hold'

    def decide(self, ctx: MarketContext) -> Signal:
        if ctx.position.is_flat:
            return Signal.ENTER
        return Signal.HOLD
