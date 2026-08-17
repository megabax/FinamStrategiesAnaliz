import os
from pathlib import Path

_TRUTHY = {'1', 'true', 'yes', 'on'}
_FALSY = {'0', 'false', 'no', 'off'}
_ENV_LOADED = False


def load_env():
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = Path(__file__).resolve().parent.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    _ENV_LOADED = True


def env_bool(name, default=False):
    load_env()
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    return default


def env_str(name, default=None):
    load_env()
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def get_database_url() -> str:
    """
    SQLAlchemy URL для MSSQL.

    Приоритет:
    1. DATABASE_URL
    2. Сборка из MSSQL_SERVER / MSSQL_DATABASE / MSSQL_DRIVER и опционально логина
    """
    from urllib.parse import quote_plus

    full = env_str('DATABASE_URL')
    if full:
        return full

    server = env_str('MSSQL_SERVER')
    if not server:
        raise RuntimeError(
            'Задайте DATABASE_URL или MSSQL_SERVER в файле .env (см. .env.example)',
        )

    database = env_str('MSSQL_DATABASE', 'FinamStrategies')
    driver = env_str('MSSQL_DRIVER', 'ODBC Driver 17 for SQL Server')
    trusted = env_bool('MSSQL_TRUSTED_CONNECTION', True)
    username = env_str('MSSQL_USERNAME')
    password = env_str('MSSQL_PASSWORD', '')

    server_q = quote_plus(server)
    driver_q = quote_plus(driver)
    if trusted:
        return (
            f'mssql+pyodbc://{server_q}/{database}'
            f'?driver={driver_q}&Trusted_Connection=yes'
        )
    if not username:
        raise RuntimeError(
            'Для SQL Authentication задайте MSSQL_USERNAME и MSSQL_PASSWORD '
            'или включите MSSQL_TRUSTED_CONNECTION=true',
        )
    return (
        f'mssql+pyodbc://{quote_plus(username)}:{quote_plus(password)}@{server_q}/{database}'
        f'?driver={driver_q}'
    )


def get_database_name(url: str | None = None) -> str:
    from sqlalchemy.engine.url import make_url

    parsed = make_url(url or get_database_url())
    if not parsed.database:
        raise RuntimeError('В DATABASE_URL не указано имя базы данных')
    return parsed.database
