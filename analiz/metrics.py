"""Расчёт метрик доходности и риска по дневной истории стратегий."""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.strategies import History, Kind, Strategy

TRADING_DAYS = 252

METRIC_COLUMNS = [
    'strategy_id',
    'period_from',
    'period_to',
    'days',
    'total_return_pct',
    'cagr_pct',
    'volatility_pct',
    'max_drawdown_pct',
    'sharpe',
    'sortino',
    'calmar',
    'positive_days_pct',
]


def _to_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def equity_curve(returns_pct: Iterable[float]) -> np.ndarray:
    r = np.asarray(list(returns_pct), dtype=float) / 100.0
    return np.cumprod(1.0 + r)


def max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    drawdown = equity / peak - 1.0
    return float(drawdown.min())


def compute_strategy_metrics(
    returns_pct: Iterable[float],
    risk_free_rate: float = 0.0,
) -> dict | None:
    """Считает метрики по ряду дневных доходностей в процентах."""
    r = np.asarray(list(returns_pct), dtype=float) / 100.0
    n = len(r)
    if n < 2:
        return None

    equity = np.cumprod(1.0 + r)
    total_return = float(equity[-1] - 1.0)
    years = n / TRADING_DAYS
    if years > 0 and equity[-1] > 0:
        cagr = float(equity[-1] ** (1.0 / years) - 1.0)
    else:
        cagr = float('nan')

    daily_std = float(r.std(ddof=1))
    volatility = daily_std * np.sqrt(TRADING_DAYS)
    excess_daily = r - risk_free_rate / TRADING_DAYS
    sharpe = (
        float(excess_daily.mean() / daily_std * np.sqrt(TRADING_DAYS))
        if daily_std > 0
        else float('nan')
    )

    downside = r[r < 0]
    if len(downside) > 1:
        downside_std = float(downside.std(ddof=1))
        sortino = (
            float(excess_daily.mean() / downside_std * np.sqrt(TRADING_DAYS))
            if downside_std > 0
            else float('nan')
        )
    else:
        sortino = float('nan')

    mdd = max_drawdown(equity)
    calmar = float(cagr / abs(mdd)) if mdd < 0 and not np.isnan(cagr) else float('nan')
    positive_days_pct = float((r > 0).sum() / n * 100.0)

    return {
        'days': n,
        'total_return_pct': round(total_return * 100.0, 3),
        'cagr_pct': round(cagr * 100.0, 3) if not np.isnan(cagr) else None,
        'volatility_pct': round(volatility * 100.0, 3),
        'max_drawdown_pct': round(mdd * 100.0, 3),
        'sharpe': round(sharpe, 4) if not np.isnan(sharpe) else None,
        'sortino': round(sortino, 4) if not np.isnan(sortino) else None,
        'calmar': round(calmar, 4) if not np.isnan(calmar) else None,
        'positive_days_pct': round(positive_days_pct, 2),
    }


def load_history_from_db(
    session: Session,
    from_date: date | datetime | None = None,
    to_date: date | datetime | None = None,
) -> pd.DataFrame:
    stmt = (
        select(
            History.strategy_id,
            History.datetime,
            History.perc_income_day,
        )
        .order_by(History.strategy_id, History.datetime)
    )
    if from_date is not None:
        stmt = stmt.where(History.datetime >= _to_date(from_date))
    if to_date is not None:
        stmt = stmt.where(History.datetime <= _to_date(to_date))

    df = pd.read_sql(stmt, session.bind)
    if df.empty:
        return df

    df['datetime'] = pd.to_datetime(df['datetime'])
    df['perc_income_day'] = pd.to_numeric(df['perc_income_day'], errors='coerce')
    return df.dropna(subset=['perc_income_day'])


def load_strategies_from_db(
    session: Session,
    exclude_archived: bool = True,
    kind_name: str | None = None,
    min_summa: int | None = None,
) -> pd.DataFrame:
    stmt = (
        select(
            Strategy.id.label('strategy_id'),
            Strategy.number,
            Strategy.name,
            Strategy.subscribers,
            Strategy.annual_income,
            Strategy.min_summa,
            Strategy.link_text,
            Strategy.archived,
            Kind.name.label('kind'),
        )
        .outerjoin(Kind, Strategy.kind_id == Kind.id)
        .order_by(Strategy.id)
    )
    if exclude_archived:
        stmt = stmt.where(Strategy.archived == False)
    if kind_name is not None:
        stmt = stmt.where(Kind.name == kind_name)
    if min_summa is not None:
        stmt = stmt.where(Strategy.min_summa >= min_summa)

    return pd.read_sql(stmt, session.bind)


def compute_metrics_dataframe(
    history_df: pd.DataFrame,
    strategies_df: pd.DataFrame | None = None,
    min_days: int = 1,
    risk_free_rate: float = 0.0,
    strategy_ids: set[int] | None = None,
) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame(columns=METRIC_COLUMNS)

    rows = []
    for strategy_id, group in history_df.groupby('strategy_id'):
        if strategy_ids is not None and strategy_id not in strategy_ids:
            continue
        if len(group) < min_days:
            continue

        metrics = compute_strategy_metrics(
            group['perc_income_day'].tolist(),
            risk_free_rate=risk_free_rate,
        )
        if metrics is None:
            continue

        rows.append({
            'strategy_id': strategy_id,
            'period_from': group['datetime'].min().date(),
            'period_to': group['datetime'].max().date(),
            **metrics,
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    if strategies_df is not None and not strategies_df.empty:
        result = result.merge(strategies_df, on='strategy_id', how='left')

    return result
