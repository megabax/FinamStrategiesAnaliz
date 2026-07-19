from dataclasses import dataclass
from datetime import datetime, time, timedelta

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from lib.load import get_summ_perc, set_period
from lib.urlutils import extract_date_text, find_start_date_element
from models.strategies import History

MATCH_TOLERANCE = 0.01

X_LOCATOR_BEG = '//*[@id="profit-calc-date-from-input"]'
X_LOCATOR_END = '//*[@id="profit-calc-date-to-input"]'


@dataclass
class VerificationResult:
    depo: float
    depo_real: float
    diff: float
    days_count: int
    period_beg: datetime
    period_end: datetime


class HistoryVerificationError(Exception):
    def __init__(self, strategy, result: VerificationResult, tolerance: float):
        self.strategy = strategy
        self.result = result
        self.tolerance = tolerance
        super().__init__(
            f'Стратегия №{strategy.number} ({strategy.name}): '
            f'расхождение {result.diff:.6f} превышает порог {tolerance:.6f} '
            f'за период {result.period_beg:%d.%m.%Y} — {result.period_end:%d.%m.%Y}. '
            f'Расчётный портфель={result.depo:.6f}, фактический={result.depo_real:.6f}',
        )


def to_datetime(value):
    if isinstance(value, datetime):
        return datetime.combine(value.date(), time.min)
    return datetime.combine(value, time.min)


def wait_for_profit_calculator(driver, timeout=20):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, 'profit-calc-date-from-input')),
    )


def read_strategy_start_date(driver):
    date_info = find_start_date_element(driver)
    if date_info is None:
        return None
    date_str = extract_date_text(date_info)
    if date_str is None:
        return None
    return datetime.strptime(date_str, '%d.%m.%Y')


def compound_history_for_period(session, strategy_id, period_beg, period_end):
    if isinstance(period_beg, datetime):
        period_beg = period_beg.date()
    if isinstance(period_end, datetime):
        period_end = period_end.date()

    depo = 1.0
    rows = (
        session.query(History)
        .filter(
            History.strategy_id == strategy_id,
            History.datetime >= period_beg,
            History.datetime <= period_end,
        )
        .order_by(History.datetime)
        .all()
    )
    for row in rows:
        if row.perc_income_day is None:
            raise ValueError(
                f'Пустой perc_income_day для strategy_id={strategy_id}, дата {row.datetime}',
            )
        depo *= 1.0 + float(row.perc_income_day) / 100.0
    return depo, rows


def verify_strategy_history(driver, session, strategy, period_beg, period_end, tolerance=MATCH_TOLERANCE):
    period_beg = to_datetime(period_beg)
    period_end = to_datetime(period_end)

    # После API-загрузки драйвер может быть не на странице стратегии
    if not strategy.link_text:
        raise ValueError(f'У стратегии №{strategy.number} пустой link_text')
    driver.get(strategy.link_text)
    wait_for_profit_calculator(driver)

    # API иногда отдаёт день раньше, чем позволяет калькулятор на сайте
    start_on_site = read_strategy_start_date(driver)
    if start_on_site is not None and period_beg < start_on_site:
        print(
            f'Период проверки скорректирован: начало {period_beg:%d.%m.%Y} -> '
            f'{start_on_site:%d.%m.%Y} (дата старта на сайте)',
        )
        period_beg = start_on_site

    if period_beg > period_end:
        raise ValueError(
            f'Пустой период проверки после корректировки: '
            f'{period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}',
        )

    period_end_exclusive = period_end + timedelta(days=1)

    depo, rows = compound_history_for_period(session, strategy.id, period_beg, period_end)
    if not rows:
        raise ValueError(
            f'Нет записей истории для проверки strategy_id={strategy.id} '
            f'за период {period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}',
        )

    try:
        set_period(driver, period_beg, period_end_exclusive, X_LOCATOR_BEG, X_LOCATOR_END)
    except Exception as exc:
        alt_beg = period_beg + timedelta(days=1)
        if alt_beg > period_end:
            raise
        print(
            f'Не удалось установить начало {period_beg:%d.%m.%Y} ({exc}). '
            f'Повтор с {alt_beg:%d.%m.%Y}',
        )
        period_beg = alt_beg
        depo, rows = compound_history_for_period(session, strategy.id, period_beg, period_end)
        if not rows:
            raise ValueError(
                f'Нет записей истории для проверки strategy_id={strategy.id} '
                f'за период {period_beg:%d.%m.%Y} — {period_end:%d.%m.%Y}',
            )
        set_period(driver, period_beg, period_end_exclusive, X_LOCATOR_BEG, X_LOCATOR_END)

    perc, perc_text = get_summ_perc(driver, None)
    if perc is None:
        raise ValueError(f'Не удалось получить доходность с сайта для стратегии №{strategy.number}')

    depo_real = 1.0 + perc / 100.0
    diff = abs(depo - depo_real)
    result = VerificationResult(
        depo=depo,
        depo_real=depo_real,
        diff=diff,
        days_count=len(rows),
        period_beg=period_beg,
        period_end=period_end,
    )
    if diff >= tolerance:
        raise HistoryVerificationError(strategy, result, tolerance)
    return result
