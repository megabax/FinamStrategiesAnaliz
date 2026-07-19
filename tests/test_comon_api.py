"""Тесты преобразования дат/процентов API comon."""

from datetime import date

from lib.comon_api import api_point_to_db_day, api_rvalue_to_perc, profit_api_to_db_series


def test_api_point_to_db_day_shift_minus_one():
    assert api_point_to_db_day('2026-07-12') == date(2026, 7, 11)
    assert api_point_to_db_day(date(2022, 5, 6)) == date(2022, 5, 5)


def test_api_rvalue_to_perc():
    assert api_rvalue_to_perc(0.01991095) == 1.991095


def test_profit_api_to_db_series():
    points = [
        {'date': '2026-07-12', 'value': 100.0, 'rValue': 0.01},
        {'date': '2026-07-11', 'value': 99.0, 'rValue': -0.02},
    ]
    series = profit_api_to_db_series(points)
    assert series[date(2026, 7, 11)] == 1.0
    assert series[date(2026, 7, 10)] == -2.0


def test_probe_profit_api_rejects_bad_payload(monkeypatch):
    from lib import comon_api

    def fake_fetch(number, timeout=20.0):
        return [{'foo': 1}]

    monkeypatch.setattr(comon_api, 'fetch_strategy_profit', fake_fetch)
    assert comon_api.probe_profit_api(109075) is False


def test_probe_profit_api_ok(monkeypatch):
    from lib import comon_api

    def fake_fetch(number, timeout=20.0):
        return [{'date': '2026-07-12', 'value': 1.0, 'rValue': 0.01}]

    monkeypatch.setattr(comon_api, 'fetch_strategy_profit', fake_fetch)
    assert comon_api.probe_profit_api(109075) is True
