"""Пропуск актуальной истории без обращения к API."""

from __future__ import annotations

from datetime import date, datetime

from lib.load import load_strategy_history_from_api


class _FakeQuery:
    def __init__(self, value):
        self._value = value

    def filter(self, *args, **kwargs):
        return self

    def scalar(self):
        return self._value


class _FakeSession:
    def __init__(self, last_in_db):
        self._last_in_db = last_in_db

    def query(self, *args, **kwargs):
        return _FakeQuery(self._last_in_db)


def test_api_skip_up_to_date_without_fetch(monkeypatch):
    fetch_calls: list[int] = []

    def fake_fetch(number, timeout=60.0):
        fetch_calls.append(number)
        return []

    monkeypatch.setattr('lib.load.fetch_strategy_profit', fake_fetch)

    end_date = datetime(2026, 8, 30)
    session = _FakeSession(last_in_db=date(2026, 8, 29))

    result = load_strategy_history_from_api(
        strategy_number=125905,
        session=session,
        strategy_id=11,
        end_date_today=end_date,
    )

    assert result is None
    assert fetch_calls == []


def test_api_load_when_behind_calls_fetch(monkeypatch):
    fetch_calls: list[int] = []

    def fake_fetch(number, timeout=60.0):
        fetch_calls.append(number)
        return [
            {'date': '2026-08-29', 'value': 1.0, 'rValue': 0.01},
            {'date': '2026-08-30', 'value': 1.01, 'rValue': 0.01},
        ]

    saved: list[date] = []

    def fake_save(strategy_id, record_datetime, perc, perc_text, replace=False, session=None):
        saved.append(record_datetime)

    monkeypatch.setattr('lib.load.fetch_strategy_profit', fake_fetch)
    monkeypatch.setattr('lib.load.save_history_record_to_db', fake_save)

    end_date = datetime(2026, 8, 30)
    session = _FakeSession(last_in_db=date(2026, 8, 27))

    result = load_strategy_history_from_api(
        strategy_number=125905,
        session=session,
        strategy_id=11,
        end_date_today=end_date,
    )

    assert fetch_calls == [125905]
    assert result is not None
    assert saved
