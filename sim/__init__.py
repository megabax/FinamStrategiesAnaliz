"""Симулятор long-only входов/выходов из стратегий comon (шаблон OOP)."""

from sim.algorithm import BuyAndHoldAlgorithm, StrategyAlgorithm
from sim.context import MarketContext
from sim.portfolio import PortfolioSimulator
from sim.strategy_sim import StrategySimulator
from sim.types import (
    Bar,
    PortfolioSnapshot,
    Position,
    PositionState,
    Signal,
    Trade,
)

__all__ = [
    'Bar',
    'BuyAndHoldAlgorithm',
    'MarketContext',
    'PortfolioSimulator',
    'PortfolioSnapshot',
    'Position',
    'PositionState',
    'Signal',
    'StrategyAlgorithm',
    'StrategySimulator',
    'Trade',
]
