"""Портфельный симулятор: несколько StrategySimulator с весами."""

from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

from sim.strategy_sim import StrategySimulator
from sim.types import Bar, PortfolioSnapshot, PositionState, Trade


class PortfolioSimulator:
    """Агрегат ног (по одной стратегии + алгоритм) с долями капитала.

    Первый релиз: одна нога, weights можно не передавать (будет 1.0).
    Несколько ног без weights → ValueError.
    """

    def __init__(
        self,
        legs: Sequence[StrategySimulator],
        weights: Mapping[int, float] | None = None,
        *,
        initial_cash: float = 1.0,
    ) -> None:
        if not legs:
            raise ValueError('нужна хотя бы одна StrategySimulator')
        if initial_cash <= 0:
            raise ValueError('initial_cash должен быть > 0')

        ids = [leg.strategy_id for leg in legs]
        if len(ids) != len(set(ids)):
            raise ValueError('strategy_id в ногах должны быть уникальны')

        self.legs: list[StrategySimulator] = list(legs)
        self.cash = float(initial_cash)
        self.equity = float(initial_cash)
        self.weights = self._normalize_weights(weights)
        self._leg_by_id = {leg.strategy_id: leg for leg in self.legs}

    def _normalize_weights(self, weights: Mapping[int, float] | None) -> dict[int, float]:
        if weights is None:
            if len(self.legs) == 1:
                return {self.legs[0].strategy_id: 1.0}
            raise ValueError(
                'для нескольких стратегий передайте weights: Mapping[strategy_id, float]',
            )

        missing = [leg.strategy_id for leg in self.legs if leg.strategy_id not in weights]
        if missing:
            raise ValueError(f'нет весов для strategy_id: {missing}')

        raw = {leg.strategy_id: float(weights[leg.strategy_id]) for leg in self.legs}
        if any(w < 0 for w in raw.values()):
            raise ValueError('веса не могут быть отрицательными')
        total = sum(raw.values())
        if total <= 0:
            raise ValueError('сумма весов должна быть > 0')
        return {sid: w / total for sid, w in raw.items()}

    def step(
        self,
        dt: date,
        bars_by_strategy: Mapping[int, Bar],
    ) -> PortfolioSnapshot:
        """Один день по всем ногам, для которых есть бар.

        Агрегация equity портфеля — следующий шаг (NotImplementedError по PnL ног).
        Сейчас собирает сделки и состояния позиций.
        """
        day_trades: list[Trade] = []
        positions: dict[int, PositionState] = {}

        for strategy_id, leg in self._leg_by_id.items():
            bar = bars_by_strategy.get(strategy_id)
            if bar is None:
                positions[strategy_id] = leg.position.state
                continue
            if bar.dt != dt:
                raise ValueError(
                    f'бар strategy_id={strategy_id}: bar.dt={bar.dt} != step dt={dt}',
                )
            trade = leg.step(bar)
            if trade is not None:
                day_trades.append(trade)
            positions[strategy_id] = leg.position.state

        # TODO: взвешенная equity по self.weights и leg.equity
        return PortfolioSnapshot(
            dt=dt,
            equity=self.equity,
            cash=self.cash,
            positions=positions,
            trades=day_trades,
        )

    def run(
        self,
        timeline: Sequence[tuple[date, Mapping[int, Bar]]],
    ) -> list[PortfolioSnapshot]:
        """Прогон по календарю: [(дата, {strategy_id: Bar}), ...]."""
        snapshots: list[PortfolioSnapshot] = []
        for dt, bars in timeline:
            snapshots.append(self.step(dt, bars))
        return snapshots
