from datetime import date
from pathlib import Path

from app.automations.holiday_reminder import HolidayReminderAutomation
from app.models.employee_models import EmployeeCreate
from app.services.employee_service import EmployeeService
from app.utils.holidays import (
    HOLIDAY_CATEGORY_CUTI_BERSAMA,
    HolidayEntry,
)


class FakeEmailService:
    def __init__(self):
        self.sent_messages = []

    def send_email(self, recipient_email: str, subject: str, body: str) -> None:
        self.sent_messages.append(
            {"recipient_email": recipient_email, "subject": subject, "body": body}
        )


def _create_employee_service(tmp_path: Path) -> EmployeeService:
    service = EmployeeService(tmp_path / "employees.json")
    service.create_employee(
        EmployeeCreate(
            full_name="Eric Wiyanto",
            email="eric@example.com",
            salary=10000000,
        )
    )
    return service


def test_should_run_only_on_last_day_of_month(tmp_path: Path):
    automation = HolidayReminderAutomation(
        employee_service_instance=_create_employee_service(tmp_path),
        email_service_instance=FakeEmailService(),
        holidays_loader=lambda: [
            HolidayEntry(holiday_date=date(2026, 3, 17), name="Nyepi")
        ],
    )

    assert automation.should_run(date(2026, 2, 28)) is True
    assert automation.should_run(date(2026, 2, 27)) is False


def test_run_sends_every_time_it_is_executed(tmp_path: Path):
    employee_service = _create_employee_service(tmp_path)
    email_service = FakeEmailService()
    automation = HolidayReminderAutomation(
        employee_service_instance=employee_service,
        email_service_instance=email_service,
        holidays_loader=lambda: [
            HolidayEntry(holiday_date=date(2026, 3, 17), name="Nyepi")
        ],
    )

    first_result = automation.run(date(2026, 2, 28))
    second_result = automation.run(date(2026, 2, 28))

    assert first_result.processed_count == 1
    assert second_result.processed_count == 1
    assert second_result.skipped_count == 0
    assert len(email_service.sent_messages) == 2
    assert "Nyepi" in email_service.sent_messages[0]["body"]


def test_run_skips_when_no_next_month_holidays(tmp_path: Path):
    employee_service = _create_employee_service(tmp_path)
    email_service = FakeEmailService()
    automation = HolidayReminderAutomation(
        employee_service_instance=employee_service,
        email_service_instance=email_service,
        holidays_loader=lambda: [
            HolidayEntry(holiday_date=date(2026, 4, 2), name="Holiday")
        ],
    )

    result = automation.run(date(2026, 2, 28))

    assert result.processed_count == 0
    assert len(email_service.sent_messages) == 0


def test_run_ignores_cuti_bersama_for_email(tmp_path: Path):
    employee_service = _create_employee_service(tmp_path)
    email_service = FakeEmailService()
    automation = HolidayReminderAutomation(
        employee_service_instance=employee_service,
        email_service_instance=email_service,
        holidays_loader=lambda: [
            HolidayEntry(
                holiday_date=date(2026, 3, 19),
                name="Cuti Bersama Nyepi",
                category=HOLIDAY_CATEGORY_CUTI_BERSAMA,
            )
        ],
    )

    result = automation.run(date(2026, 2, 28))

    assert result.processed_count == 0
    assert "No national holidays configured" in result.message
    assert len(email_service.sent_messages) == 0
