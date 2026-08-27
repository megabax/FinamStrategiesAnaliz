"""Загрузка дневных баров стратегии из MSSQL."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.strategies import History, Strategy
from sim.types import Bar


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def load_bars_by_strategy_id(
    session: Session,
    strategy_id: int,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[Bar]:
    """Дневная история → список Bar по internal strategy_id."""
    stmt = (
        select(History.datetime, History.perc_income_day)
        .where(History.strategy_id == strategy_id)
        .order_by(History.datetime)
    )
    if from_date is not None:
        stmt = stmt.where(History.datetime >= from_date)
    if to_date is not None:
        stmt = stmt.where(History.datetime <= to_date)

    rows = session.execute(stmt).all()
    bars: list[Bar] = []
    for dt_raw, perc in rows:
        if perc is None:
            continue
        bars.append(
            Bar(
                dt=_as_date(dt_raw),
                strategy_id=strategy_id,
                perc_income_day=float(perc),
            ),
        )
    return bars


def load_strategy_and_bars_by_number(
    session: Session,
    number: int,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> tuple[Strategy, list[Bar]]:
    """Найти стратегию по number (comon) и загрузить бары."""
    strategy = session.query(Strategy).filter(Strategy.number == number).first()
    if strategy is None:
        raise LookupError(f'Стратегия с номером {number} не найдена в базе.')
    bars = load_bars_by_strategy_id(
        session,
        strategy.id,
        from_date=from_date,
        to_date=to_date,
    )
    return strategy, bars
