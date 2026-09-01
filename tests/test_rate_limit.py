"""Тесты случайных пауз comon (lib/rate_limit)."""

from __future__ import annotations

import pytest

from lib.rate_limit import PauseRange, reset_rate_limit_settings


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_rate_limit_settings()
    yield
    reset_rate_limit_settings()


def test_pause_range_sample_bounds(monkeypatch):
    monkeypatch.setattr('lib.rate_limit.random.uniform', lambda lo, hi: lo)
    assert PauseRange(0.5, 2.0).sample() == 0.5
    monkeypatch.setattr('lib.rate_limit.random.uniform', lambda lo, hi: hi)
    assert PauseRange(0.5, 2.0).sample() == 2.0


def test_pause_range_zero_when_disabled_range():
    assert PauseRange(0, 0).sample() == 0.0
    assert PauseRange(-1, -2).sample() == 0.0


def test_pause_api_sleeps_random(monkeypatch):
    slept: list[float] = []

    def fake_sleep(sec: float) -> None:
        slept.append(sec)

    monkeypatch.setattr('lib.rate_limit.time.sleep', fake_sleep)
    monkeypatch.setenv('COMON_PAUSES_ENABLED', 'true')
    monkeypatch.setenv('COMON_API_PAUSE_MIN', '0.4')
    monkeypatch.setenv('COMON_API_PAUSE_MAX', '0.4')
    reset_rate_limit_settings()

    from lib.rate_limit import pause_api

    pause_api()
    assert slept == [0.4]


def test_pause_disabled(monkeypatch):
    slept: list[float] = []

    monkeypatch.setattr('lib.rate_limit.time.sleep', lambda s: slept.append(s))
    monkeypatch.setenv('COMON_PAUSES_ENABLED', 'false')
    monkeypatch.setenv('COMON_API_PAUSE_MIN', '5')
    monkeypatch.setenv('COMON_API_PAUSE_MAX', '10')
    reset_rate_limit_settings()

    from lib.rate_limit import pause_api

    pause_api()
    assert slept == []
