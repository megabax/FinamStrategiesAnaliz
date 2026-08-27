"""Базовые типы симулятора long-only входов/выходов."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum, auto


class Signal(Enum):
    """Решение алгоритма на текущем шаге. Шортов нет."""

    HOLD = auto()
    ENTER = auto()  # купить / войти в стратегию
    EXIT = auto()  # продать / выйти из стратегии


class PositionState(Enum):
    """Состояние позиции по одной стратегии."""

    FLAT = auto()
    LONG = auto()


@dataclass(frozen=True)
class Bar:
    """Один день истории стратегии (как строка history)."""

    dt: date
    strategy_id: int
    perc_income_day: float


@dataclass(frozen=True)
class Trade:
    """Исполненная сделка (вход или выход)."""

    dt: date
    strategy_id: int
    side: Signal  # только ENTER или EXIT
    qty: float = 1.0
    # Заглушки под будущий учёт цены / доли капитала
    price: float | None = None
    weight: float | None = None


@dataclass
class Position:
    """Текущая позиция по стратегии (расширяемый каркас)."""

    state: PositionState = PositionState.FLAT
    qty: float = 0.0
    entry_date: date | None = None

    @property
    def is_long(self) -> bool:
        return self.state is PositionState.LONG

    @property
    def is_flat(self) -> bool:
        return self.state is PositionState.FLAT


@dataclass
class PortfolioSnapshot:
    """Состояние портфеля на дату (агрегат по ногам)."""

    dt: date
    equity: float
    cash: float
    positions: dict[int, PositionState] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
