"""Регрессия: write_mismatches_csv не падает на diff с десятичной запятой."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

from lib.csv_export import CSV_DELIMITER, CSV_ENCODING, parse_decimal

ROOT = Path(__file__).resolve().parents[1]


def _load_verify_module():
    """Загружает корневой test.py без конфликта с пакетом tests."""
    path = ROOT / 'test.py'
    spec = importlib.util.spec_from_file_location('strategy_verify', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def verify_module():
    return _load_verify_module()


def _mismatch(diff, strategy_id=1, number=100001, name='A'):
    return {
        'strategy_id': strategy_id,
        'number': number,
        'name': name,
        'depo': '1,980712',
        'depo_real': '1,977800',
        'diff': diff,
        'period_beg': '01.04.2022',
        'period_end': '25.11.2025',
        'days_count': 1334,
        'link': 'https://www.comon.ru/strategies/100001/',
    }


def test_write_mismatches_csv_sorts_comma_decimal_diffs(tmp_path, verify_module):
    """
    После format_csv_record в mismatches лежат строки вида «0,011540».
    Сортировка через float(...) давала ValueError — должен работать parse_decimal.
    """
    mismatches = [
        _mismatch('0,002912', strategy_id=1, number=1, name='small'),
        _mismatch('0,011540', strategy_id=2, number=2, name='large'),
        _mismatch('0,004565', strategy_id=3, number=3, name='mid'),
    ]
    out = tmp_path / 'mismatches.csv'

    count = verify_module.write_mismatches_csv(out, mismatches)

    assert count == 3
    with out.open(encoding=CSV_ENCODING, newline='') as f:
        rows = list(csv.DictReader(f, delimiter=CSV_DELIMITER))

    assert [row['name'] for row in rows] == ['large', 'mid', 'small']
    assert [row['rank'] for row in rows] == ['1', '2', '3']
    assert parse_decimal(rows[0]['diff']) == pytest.approx(0.01154)
    assert CSV_DELIMITER in out.read_text(encoding=CSV_ENCODING)


def test_parse_decimal_accepts_comma_and_dot():
    assert parse_decimal('0,011540') == pytest.approx(0.01154)
    assert parse_decimal('0.011540') == pytest.approx(0.01154)
    assert parse_decimal(0.01154) == pytest.approx(0.01154)
