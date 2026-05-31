from datetime import date

from app.services.proration_service import (
    calculate_prorated_amount,
    calculate_worked_days_for_month,
    calculate_working_days,
    calculate_working_days_in_range,
)


def test_calculate_working_days_in_range_excludes_weekends_and_holidays():
    start = date(2026, 1, 5)  # Monday
    end = date(2026, 1, 11)   # Sunday
    holidays = {date(2026, 1, 7)}
    assert calculate_working_days_in_range(start, end, holidays) == 4


def test_calculate_prorated_amount():
    assert calculate_prorated_amount(1000, 10, 20) == 500


def test_calculate_working_days_defaults_to_weekdays_only():
    assert calculate_working_days(2026, 5, holidays=set()) == 21


def test_calculate_worked_days_for_month_defaults_to_weekdays_only():
    assert calculate_worked_days_for_month(2026, 5, holidays=set()) == 21


def test_calculate_working_days_excludes_confirmed_holidays_when_provided():
    holidays = {date(2026, 5, 1), date(2026, 5, 14), date(2026, 5, 27)}
    assert calculate_working_days(2026, 5, holidays=holidays) == 18
