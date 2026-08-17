"""Тесты сборки DATABASE_URL из окружения."""

import pytest

from lib.env import get_database_name, get_database_url


def test_get_database_url_from_full_env(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'mssql+pyodbc://localhost/FinamStrategies?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes',
    )
    url = get_database_url()
    assert url.startswith('mssql+pyodbc://localhost/FinamStrategies')
    assert 'MEGABAX' not in url
    assert get_database_name(url) == 'FinamStrategies'


def test_get_database_url_from_parts(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('MSSQL_SERVER', r'localhost\SQLEXPRESS')
    monkeypatch.setenv('MSSQL_DATABASE', 'FinamStrategies')
    monkeypatch.setenv('MSSQL_DRIVER', 'ODBC Driver 17 for SQL Server')
    monkeypatch.setenv('MSSQL_TRUSTED_CONNECTION', 'true')
    url = get_database_url()
    assert 'localhost' in url
    assert 'MEGABAX' not in url
    assert 'FinamStrategies' in url
    assert get_database_name(url) == 'FinamStrategies'


def test_get_database_url_requires_config(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.delenv('MSSQL_SERVER', raising=False)
    with pytest.raises(RuntimeError, match='DATABASE_URL или MSSQL_SERVER'):
        get_database_url()
