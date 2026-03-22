from __future__ import annotations

import calendar
from datetime import date
from typing import Callable, List, Optional, Protocol

from app.automations.base import Automation, AutomationResult
from app.services.employee_service import EmployeeService, employee_service
from app.utils.holidays import (
    HOLIDAY_CATEGORY_LIBUR_NASIONAL,
    HolidayEntry,
    load_holiday_entries,
)


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


class HolidayReminderEmailService(Protocol):
    def send_email(self, recipient_email: str, subject: str, body: str) -> None:
        ...


class HolidayReminderAutomation(Automation):
    name = "holiday-reminder"

    def __init__(
        self,
        employee_service_instance: EmployeeService = employee_service,
        email_service_instance: Optional[HolidayReminderEmailService] = None,
        holidays_loader: Callable[[], List[HolidayEntry]] = load_holiday_entries,
    ):
        if email_service_instance is None:
            from app.services.email_service import email_service

            email_service_instance = email_service

        self.employee_service = employee_service_instance
        self.email_service = email_service_instance
        self.holidays_loader = holidays_loader

    def should_run(self, run_date: date) -> bool:
        return run_date.day == calendar.monthrange(run_date.year, run_date.month)[1]

    def run(self, run_date: date) -> AutomationResult:
        year, month = _next_month(run_date.year, run_date.month)
        month_label = date(year, month, 1).strftime("%B %Y")

        holidays = sorted(
            (
                holiday
                for holiday in self.holidays_loader()
                if holiday.holiday_date.year == year
                and holiday.holiday_date.month == month
                and holiday.category == HOLIDAY_CATEGORY_LIBUR_NASIONAL
            ),
            key=lambda holiday: (holiday.holiday_date, holiday.name),
        )
        if not holidays:
            return AutomationResult(
                automation=self.name,
                ran=True,
                message=f"No national holidays configured for {month_label}",
            )

        employees = self.employee_service.list_employees()
        subject = f"Public holiday reminder for {month_label}"
        holiday_lines = "\n".join(
            f"- {holiday.holiday_date.strftime('%A, %d %B %Y')} — {holiday.name}"
            for holiday in holidays
        )

        processed = 0
        failed = 0

        for employee in employees:
            first_name = employee.full_name.split(" ")[0]
            body = (
                f"Hi {first_name},\n\n"
                f"Here are the public holidays for {month_label}:\n"
                f"{holiday_lines}\n\n"
                "Please plan your month accordingly.\n\n"
                "Best regards,"
            )

            try:
                self.email_service.send_email(employee.email, subject, body)
            except Exception:
                failed += 1
                continue

            processed += 1

        return AutomationResult(
            automation=self.name,
            ran=True,
            processed_count=processed,
            failed_count=failed,
            message=(
                f"Holiday reminders for {month_label}: "
                f"sent={processed}, failed={failed}"
            ),
        )


def get_holiday_reminder_automation() -> HolidayReminderAutomation:
    return HolidayReminderAutomation()
