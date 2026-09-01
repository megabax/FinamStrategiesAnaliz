"""Клиент публичного API comon.ru для истории доходности стратегий."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from lib.rate_limit import pause_api

import requests

PROFIT_URL = 'https://www.comon.ru/api/v1/strategies/{number}/profit'

# В API rValue на дату D соответствует perc_income_day в БД на дату D-1
# (день калькулятора [D-1, D) на сайте).
API_TO_DB_DATE_SHIFT_DAYS = -1


def _headers(number: int) -> dict[str, str]:
    return {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'Referer': f'https://www.comon.ru/strategies/{number}/',
        'Origin': 'https://www.comon.ru',
    }


def fetch_strategy_profit(number: int, timeout: float = 60.0) -> list[dict]:
    """
    Загружает историю из GET /api/v1/strategies/{number}/profit.

    Каждый элемент: date (str YYYY-MM-DD), value (float), rValue (float, доля за день).
    """
    url = PROFIT_URL.format(number=number)
    pause_api()
    response = requests.get(url, headers=_headers(number), timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or 'data' not in payload:
        raise ValueError(f'Неожиданный ответ API: {payload!r}')
    if payload.get('error'):
        raise ValueError(f'API вернул error: {payload["error"]!r}')
    data = payload['data']
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f'Поле data должно быть списком, получено: {type(data).__name__}')
    return data


def probe_profit_api(sample_number: int, timeout: float = 20.0) -> bool:
    """
    Проверяет, что недокументированный profit API отвечает и отдаёт ожидаемую структуру.
    """
    try:
        points = fetch_strategy_profit(sample_number, timeout=timeout)
    except Exception as exc:
        print(f'Проверка API profit: недоступен ({exc})')
        return False

    if not points:
        print('Проверка API profit: пустой data')
        return False

    sample = points[0]
    if not isinstance(sample, dict) or 'date' not in sample or 'rValue' not in sample:
        print(f'Проверка API profit: неожиданная структура точки {sample!r}')
        return False

    try:
        date.fromisoformat(str(sample['date']))
        float(sample['rValue'])
    except (TypeError, ValueError) as exc:
        print(f'Проверка API profit: не удалось разобрать точку ({exc})')
        return False

    print(f'Проверка API profit: OK (number={sample_number}, точек={len(points)})')
    return True


def api_point_to_db_day(api_date: date | datetime | str) -> date:
    """Дата в БД, соответствующая точке API с указанной date."""
    if isinstance(api_date, str):
        api_date = date.fromisoformat(api_date)
    elif isinstance(api_date, datetime):
        api_date = api_date.date()
    return api_date + timedelta(days=API_TO_DB_DATE_SHIFT_DAYS)


def api_rvalue_to_perc(r_value: float) -> float:
    """Доля дневной доходности API → процент как в history.perc_income_day."""
    return float(r_value) * 100.0


def profit_api_to_db_series(points: list[dict]) -> dict[date, float]:
    """
    Преобразует ответ API в словарь {дата_БД: perc_income_day}.

    Точки с value=0 и rValue=0 на старте стратегии обычно остаются
    (первая точка часто нулевая).
    """
    result: dict[date, float] = {}
    for point in points:
        db_day = api_point_to_db_day(point['date'])
        result[db_day] = api_rvalue_to_perc(point['rValue'])
    return result
