"""Случайные паузы между обращениями к comon (API и Selenium)."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from lib.env import env_bool, env_float


@dataclass(frozen=True)
class PauseRange:
    """Равномерная случайная задержка в [min_sec, max_sec]."""

    min_sec: float
    max_sec: float

    def sample(self) -> float:
        if self.min_sec <= 0 and self.max_sec <= 0:
            return 0.0
        lo = min(self.min_sec, self.max_sec)
        hi = max(self.min_sec, self.max_sec)
        if hi <= 0:
            return 0.0
        return random.uniform(lo, hi)


@dataclass(frozen=True)
class RateLimitSettings:
    enabled: bool
    api: PauseRange
    selenium_page: PauseRange
    selenium_calc: PauseRange
    selenium_retry: PauseRange
    selenium_day: PauseRange
    strategy: PauseRange

    @classmethod
    def from_env(cls) -> RateLimitSettings:
        return cls(
            enabled=env_bool('COMON_PAUSES_ENABLED', True),
            api=PauseRange(
                env_float('COMON_API_PAUSE_MIN', 0.3),
                env_float('COMON_API_PAUSE_MAX', 1.0),
            ),
            selenium_page=PauseRange(
                env_float('COMON_SELENIUM_PAGE_PAUSE_MIN', 0.5),
                env_float('COMON_SELENIUM_PAGE_PAUSE_MAX', 1.5),
            ),
            selenium_calc=PauseRange(
                env_float('COMON_SELENIUM_CALC_PAUSE_MIN', 0.4),
                env_float('COMON_SELENIUM_CALC_PAUSE_MAX', 1.0),
            ),
            selenium_retry=PauseRange(
                env_float('COMON_SELENIUM_RETRY_PAUSE_MIN', 1.0),
                env_float('COMON_SELENIUM_RETRY_PAUSE_MAX', 2.5),
            ),
            selenium_day=PauseRange(
                env_float('COMON_SELENIUM_DAY_PAUSE_MIN', 0.2),
                env_float('COMON_SELENIUM_DAY_PAUSE_MAX', 0.8),
            ),
            strategy=PauseRange(
                env_float('COMON_STRATEGY_PAUSE_MIN', 1.0),
                env_float('COMON_STRATEGY_PAUSE_MAX', 3.0),
            ),
        )


_settings: RateLimitSettings | None = None


def get_rate_limit_settings() -> RateLimitSettings:
    global _settings
    if _settings is None:
        _settings = RateLimitSettings.from_env()
    return _settings


def reset_rate_limit_settings() -> None:
    """Сброс кэша настроек (для тестов)."""
    global _settings
    _settings = None


def _sleep_range(pause_range: PauseRange, *, scale: float = 1.0) -> float:
    settings = get_rate_limit_settings()
    if not settings.enabled:
        return 0.0
    delay = pause_range.sample() * scale
    if delay > 0:
        time.sleep(delay)
    return delay


def pause_api(*, scale: float = 1.0) -> float:
    """Пауза перед/после HTTP-запроса к API comon."""
    return _sleep_range(get_rate_limit_settings().api, scale=scale)


def pause_selenium_page(*, scale: float = 1.0) -> float:
    """Пауза после загрузки/скролла страницы."""
    return _sleep_range(get_rate_limit_settings().selenium_page, scale=scale)


def pause_selenium_calc(*, scale: float = 1.0) -> float:
    """Пауза после клика по калькулятору доходности."""
    return _sleep_range(get_rate_limit_settings().selenium_calc, scale=scale)


def pause_selenium_retry(*, scale: float = 1.0) -> float:
    """Пауза при повторном чтении результата калькулятора."""
    return _sleep_range(get_rate_limit_settings().selenium_retry, scale=scale)


def pause_selenium_day(*, scale: float = 1.0) -> float:
    """Пауза между днями в цикле Selenium-загрузки истории."""
    return _sleep_range(get_rate_limit_settings().selenium_day, scale=scale)


def pause_between_strategies(*, scale: float = 1.0) -> float:
    """Пауза между стратегиями в массовой загрузке."""
    return _sleep_range(get_rate_limit_settings().strategy, scale=scale)
