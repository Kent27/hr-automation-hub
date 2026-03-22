from app.automations.holiday_reminder import get_holiday_reminder_automation
from app.automations.holiday_sync import holiday_sync_automation
from app.automations.payslip import payslip_automation
from app.automations.runner import AutomationRunner


automation_runner = AutomationRunner(
    [
        holiday_sync_automation,
        get_holiday_reminder_automation(),
        payslip_automation,
    ]
)
