"""Контекст рынка, который алгоритм видит на одном шаге симуляции."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sim.types import Bar, Position


@dataclass(frozen=True)
class MarketContext:
    """Снимок для StrategyAlgorithm.decide.

    history — бары строго до текущего (без текущего bar), read-only последовательность.
    portfolio_value / leg_weight — для будущих мультистратегийных алгоритмов.
    """

    bar: Bar
    history: Sequence[Bar]
    position: Position
    portfolio_value: float | None = None
    leg_weight: float | None = None
