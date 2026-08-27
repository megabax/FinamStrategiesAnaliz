"""Симулятор одной стратегии: long-only вход/выход по алгоритму."""

from __future__ import annotations

from sim.algorithm import StrategyAlgorithm
from sim.context import MarketContext
from sim.types import Bar, Position, PositionState, Signal, Trade


class StrategySimulator:
    """Связка одной стратегии comon с одним StrategyAlgorithm.

    Шортов нет: ENTER только из FLAT, EXIT только из LONG, иначе сигнал игнорируется.
    Начисление PnL по perc_income_day — следующий шаг (см. _apply_daily_return).
    """

    def __init__(
        self,
        strategy_id: int,
        algorithm: StrategyAlgorithm,
        *,
        initial_cash: float = 1.0,
    ) -> None:
        if initial_cash <= 0:
            raise ValueError('initial_cash должен быть > 0')
        self.strategy_id = strategy_id
        self.algorithm = algorithm
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.equity = float(initial_cash)
        self.position = Position()
        self._history: list[Bar] = []
        self.trades: list[Trade] = []

    def step(self, bar: Bar) -> Trade | None:
        """Один торговый день: сигнал алгоритма → сделка (если есть) → учёт бара.

        Raises:
            ValueError: если bar.strategy_id не совпадает с симулятором.
        """
        if bar.strategy_id != self.strategy_id:
            raise ValueError(
                f'bar.strategy_id={bar.strategy_id} != simulator.strategy_id={self.strategy_id}',
            )

        ctx = MarketContext(
            bar=bar,
            history=tuple(self._history),
            position=self.position,
        )
        raw_signal = self.algorithm.decide(ctx)
        effective = self._resolve_long_only(raw_signal)

        trade: Trade | None = None
        if effective is Signal.ENTER:
            trade = self._enter(bar)
        elif effective is Signal.EXIT:
            trade = self._exit(bar)

        self._history.append(bar)
        # TODO: следующий шаг — self._apply_daily_return(bar) (PnL только в LONG).
        # Метод объявлен ниже и пока бросает NotImplementedError.
        return trade

    def run(self, bars: list[Bar] | tuple[Bar, ...]) -> list[Trade]:
        """Прогнать последовательность баров; вернуть список сделок.

        Пока без начисления дневной доходности (см. _apply_daily_return).
        """
        trades: list[Trade] = []
        for bar in bars:
            trade = self.step(bar)
            if trade is not None:
                trades.append(trade)
        return trades

    def _resolve_long_only(self, signal: Signal) -> Signal | None:
        """Отфильтровать невозможные для long-only действия.

        Returns:
            ENTER / EXIT для исполнения или None (HOLD либо игнор).
        """
        if signal is Signal.HOLD:
            return None
        if signal is Signal.ENTER:
            if self.position.is_long:
                return None  # уже в позиции — не удваиваем
            return Signal.ENTER
        if signal is Signal.EXIT:
            if self.position.is_flat:
                return None  # нечего продавать — не шортим
            return Signal.EXIT
        raise ValueError(f'Неизвестный сигнал: {signal!r}')

    def _enter(self, bar: Bar) -> Trade:
        self.position.state = PositionState.LONG
        self.position.qty = 1.0
        self.position.entry_date = bar.dt
        trade = Trade(
            dt=bar.dt,
            strategy_id=self.strategy_id,
            side=Signal.ENTER,
            qty=self.position.qty,
        )
        self.trades.append(trade)
        self.algorithm.on_fill(trade)
        return trade

    def _exit(self, bar: Bar) -> Trade:
        qty = self.position.qty
        self.position.state = PositionState.FLAT
        self.position.qty = 0.0
        self.position.entry_date = None
        trade = Trade(
            dt=bar.dt,
            strategy_id=self.strategy_id,
            side=Signal.EXIT,
            qty=qty,
        )
        self.trades.append(trade)
        self.algorithm.on_fill(trade)
        return trade

    def _apply_daily_return(self, bar: Bar) -> None:
        """Начислить perc_income_day на equity, только если позиция LONG.

        Следующий шаг реализации::

            if self.position.is_long:
                self.equity *= 1.0 + bar.perc_income_day / 100.0

        Сейчас не вызывается из step/run, чтобы можно было отрабатывать сигналы
        и сделки без имитации готового бэктеста.
        """
        raise NotImplementedError(
            'Начисление дневной доходности пока не реализовано '
            '(StrategySimulator._apply_daily_return).',
        )
