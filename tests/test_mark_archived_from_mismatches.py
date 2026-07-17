"""Unit-тесты логики mark_archived_from_mismatches без Selenium."""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
import random

import pytest

from lib.csv_export import parse_decimal

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / 'mark_archived_from_mismatches.py'
    spec = importlib.util.spec_from_file_location('mark_archived_from_mismatches', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def mod():
    return _load_module()


def test_is_depo_real_one_accepts_csv_comma(mod):
    assert mod.is_depo_real_one('1,000000')
    assert mod.is_depo_real_one(1.0)
    assert not mod.is_depo_real_one('1,000001', eps=1e-9)
    assert not mod.is_depo_real_one('271,865400')


def test_random_subperiod_stays_inside_bounds(mod):
    beg = datetime(2020, 1, 1)
    end = datetime(2020, 2, 1)  # exclusive
    rng = random.Random(42)
    for _ in range(50):
        sub_beg, sub_end = mod.random_subperiod(beg, end, rng)
        assert beg <= sub_beg < sub_end <= end
        assert (sub_end - sub_beg).days >= 1


def test_load_mismatch_sample_finds_depo_one_candidates(mod):
    sample = ROOT / 'reports' / 'mismatches_for_reload4.csv'
    if not sample.exists():
        pytest.skip('нет образца reports/mismatches_for_reload4.csv')
    rows = mod.load_mismatch_rows(sample)
    candidates = [row for row in rows if mod.is_depo_real_one(row['depo_real'])]
    assert len(rows) >= len(candidates) > 0
    assert all(parse_decimal(row['depo_real']) == pytest.approx(1.0) for row in candidates)
