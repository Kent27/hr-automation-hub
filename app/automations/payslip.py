from __future__ import annotations

from datetime import date

from app.automations.base import Automation, AutomationResult
from app.services.employee_service import EmployeeService, employee_service
from app.services.payslip_service import PayslipService, payslip_service


class PayslipAutomation(Automation):
    name = "payslip-send-all"

    def __init__(
        self,
        employee_service_instance: EmployeeService = employee_service,
        payslip_service_instance: PayslipService = payslip_service,
    ):
        self.employee_service = employee_service_instance
        self.payslip_service = payslip_service_instance

    def should_run(self, run_date: date) -> bool:
        return False

    def run(self, run_date: date) -> AutomationResult:
        month = run_date.strftime("%Y-%m")
        processed = self.send_all(month)
        return AutomationResult(
            automation=self.name,
            ran=True,
            processed_count=processed,
            message=f"Sent payslips for {processed} employee(s) for {month}",
        )

    def generate_all(self, month: str) -> int:
        processed = 0
        for employee in self.employee_service.list_employees():
            self.payslip_service.generate_payslip(employee.id, month)
            processed += 1
        return processed

    def send_all(self, month: str) -> int:
        processed = 0
        for employee in self.employee_service.list_employees():
            self.payslip_service.send_payslip(employee.id, month)
            processed += 1
        return processed


payslip_automation = PayslipAutomation()
