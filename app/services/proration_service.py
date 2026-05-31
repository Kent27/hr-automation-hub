from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional, Set

from app.utils.holidays import load_confirmed_holidays


def calculate_working_days_in_range(
    start_date: date,
    end_date: date,
    holidays: Optional[Set[date]] = None,
) -> int:
    if start_date > end_date:
        return 0
    holidays = holidays or set()
    total = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in holidays:
            total += 1
        current += timedelta(days=1)
    return total


def calculate_working_days(year: int, month: int, holidays: Optional[Set[date]] = None) -> int:
    holidays = holidays if holidays is not None else load_confirmed_holidays()
    last_day = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    return calculate_working_days_in_range(start_date, end_date, holidays)


def calculate_prorated_amount(amount: float, worked_days: int, total_working_days: int) -> float:
    if total_working_days <= 0:
        return amount
    ratio = worked_days / total_working_days
    return round(amount * ratio, 2)


def calculate_worked_days_for_month(
    year: int,
    month: int,
    join_date: Optional[date] = None,
    holidays: Optional[Set[date]] = None,
) -> int:
    holidays = holidays if holidays is not None else load_confirmed_holidays()
    last_day = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    if join_date and join_date.year == year and join_date.month == month:
        start_date = join_date
    end_date = date(year, month, last_day)
    return calculate_working_days_in_range(start_date, end_date, holidays)
