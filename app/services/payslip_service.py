from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from app.config import COMPANY_NAME
from app.models.payslip_models import PayslipBenefit, PayslipData
from app.services.claim_service import ClaimService, claim_service
from app.services.employee_service import EmployeeService, employee_service
from app.services.payslip_generator import generate_payslip_pdf
from app.services.proration_service import (
    calculate_prorated_amount,
    calculate_worked_days_for_month,
    calculate_working_days,
)
from app.services.email_service import EmailService, email_service


def _parse_month(month: str) -> Tuple[int, int]:
    try:
        parsed = datetime.strptime(month, "%Y-%m")
        return parsed.year, parsed.month
    except ValueError:
        raise ValueError("Month must be in YYYY-MM format")


class PayslipService:
    def __init__(
        self,
        employee_service_instance: EmployeeService = employee_service,
        claim_service_instance: ClaimService = claim_service,
        email_service_instance: EmailService = email_service,
    ):
        self.employee_service = employee_service_instance
        self.claim_service = claim_service_instance
        self.email_service = email_service_instance

    def _build_payslip_data(
        self,
        employee_id: str,
        month: str,
        worked_days: Optional[int] = None,
    ) -> PayslipData:
        employee = self.employee_service.get_employee(employee_id)
        if not employee:
            raise ValueError("Employee not found")

        year, month_index = _parse_month(month)
        total_working_days = calculate_working_days(year, month_index)
        if worked_days is None:
            worked_days = calculate_worked_days_for_month(
                year, month_index, join_date=employee.join_date
            )

        prorated_salary = calculate_prorated_amount(
            employee.salary, worked_days, total_working_days
        )

        claims = self.claim_service.list_claims(employee_id=employee_id, month=month)
        benefits_summary = []
        total_benefits = 0.0
        for benefit in employee.benefits:
            claimed = sum(
                claim.amount_raw for claim in claims if claim.benefit_type == benefit.type
            )
            approved = sum(
                claim.amount_approved
                for claim in claims
                if claim.benefit_type == benefit.type
            )
            benefits_summary.append(
                PayslipBenefit(
                    type=benefit.type,
                    claimed=claimed,
                    approved=approved,
                    limit=benefit.limit,
                )
            )
            total_benefits += approved

        days_unworked = max(total_working_days - worked_days, 0)
        prorated_deduction = max(employee.salary - prorated_salary, 0)
        total_earnings = employee.salary + total_benefits
        total_deductions = prorated_deduction
        net_pay = total_earnings - total_deductions
        pay_period_label = datetime(year, month_index, 1).strftime("%B %Y")
        return PayslipData(
            employee_id=employee.id,
            employee_name=employee.full_name,
            employee_email=employee.email,
            designation=employee.designation,
            date_of_joining=employee.join_date,
            period=month,
            pay_period_label=pay_period_label,
            company_name=COMPANY_NAME,
            base_salary=employee.salary,
            total_working_days=total_working_days,
            worked_days=worked_days,
            days_unworked=days_unworked,
            prorated_salary=prorated_salary,
            prorated_deduction=prorated_deduction,
            benefits=benefits_summary,
            total_benefits=total_benefits,
            total_earnings=total_earnings,
            total_deductions=total_deductions,
            net_pay=net_pay,
            generated_at=datetime.utcnow(),
        )

    def generate_payslip(
        self,
        employee_id: str,
        month: str,
        worked_days: Optional[int] = None,
    ) -> Tuple[PayslipData, str]:
        payslip_data = self._build_payslip_data(employee_id, month, worked_days)
        pdf_path = generate_payslip_pdf(payslip_data)
        return payslip_data, str(pdf_path)

    def send_payslip(
        self,
        employee_id: str,
        month: str,
        worked_days: Optional[int] = None,
        pdf_path: Optional[str] = None,
    ) -> Tuple[PayslipData, str]:
        if pdf_path is not None:
            payslip_data = self._build_payslip_data(employee_id, month, worked_days)
            path_to_send = pdf_path
        else:
            payslip_data, path_to_send = self.generate_payslip(
                employee_id, month, worked_days
            )
        self.email_service.send_payslip(payslip_data, path_to_send)
        return payslip_data, path_to_send


payslip_service = PayslipService()
