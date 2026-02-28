from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer

from app.models.employee_models import Benefit, EmployeeCreate, EmployeeUpdate
from app.services.claim_service import claim_service
from app.services.employee_service import employee_service
from app.services.email_service import email_service
from app.services.payslip_service import payslip_service

app = typer.Typer(help="Payslip Email Automator")
employee_app = typer.Typer(help="Manage employees")
claim_app = typer.Typer(help="Manage claims")
payslip_app = typer.Typer(help="Generate and send payslips")
auth_app = typer.Typer(help="Authentication helpers")

app.add_typer(employee_app, name="employee")
app.add_typer(claim_app, name="claim")
app.add_typer(payslip_app, name="payslip")
app.add_typer(auth_app, name="auth")


def _default_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _parse_benefits(values: Optional[List[str]]) -> List[Benefit]:
    benefits: List[Benefit] = []
    for raw in values or []:
        if ":" not in raw:
            raise typer.BadParameter("Benefit must be in type:limit format")
        benefit_type, limit_str = raw.split(":", 1)
        benefits.append(Benefit(type=benefit_type.strip(), limit=float(limit_str)))
    return benefits


@employee_app.command("add")
def add_employee(
    full_name: str,
    email: str,
    salary: float,
    designation: Optional[str] = typer.Option(None, "--designation"),
    benefit: Optional[List[str]] = typer.Option(None, "--benefit"),
    join_date: Optional[str] = typer.Option(None, "--join-date"),
):
    join_date_value = datetime.fromisoformat(join_date).date() if join_date else None
    benefits = _parse_benefits(benefit)
    employee = employee_service.create_employee(
        EmployeeCreate(
            full_name=full_name,
            email=email,
            designation=designation,
            salary=salary,
            benefits=benefits,
            join_date=join_date_value,
        )
    )
    typer.echo(json.dumps(employee.model_dump(), indent=2, default=str))


@employee_app.command("list")
def list_employees():
    employees = [emp.model_dump() for emp in employee_service.list_employees()]
    typer.echo(json.dumps(employees, indent=2, default=str))


@employee_app.command("update")
def update_employee(
    employee_id: str,
    full_name: Optional[str] = typer.Option(None, "--full-name"),
    email: Optional[str] = typer.Option(None, "--email"),
    designation: Optional[str] = typer.Option(None, "--designation"),
    salary: Optional[float] = typer.Option(None, "--salary"),
    benefit: Optional[List[str]] = typer.Option(None, "--benefit"),
    join_date: Optional[str] = typer.Option(None, "--join-date"),
):
    join_date_value = datetime.fromisoformat(join_date).date() if join_date else None
    benefits = _parse_benefits(benefit) if benefit is not None else None
    employee = employee_service.update_employee(
        employee_id,
        EmployeeUpdate(
            full_name=full_name,
            email=email,
            designation=designation,
            salary=salary,
            benefits=benefits,
            join_date=join_date_value,
        ),
    )
    if not employee:
        raise typer.Exit(code=1)
    typer.echo(json.dumps(employee.model_dump(), indent=2, default=str))


@employee_app.command("remove")
def remove_employee(employee_id: str):
    deleted = employee_service.delete_employee(employee_id)
    if not deleted:
        raise typer.Exit(code=1)
    typer.echo("Employee removed")


@claim_app.command("add")
def add_claim(
    employee_id: str,
    benefit_type: str,
    invoice_path: Path,
    month: str = typer.Option(None, "--month"),
    amount: Optional[float] = typer.Option(None, "--amount"),
):
    claim = claim_service.add_claim(
        employee_id=employee_id,
        benefit_type=benefit_type,
        invoice_path=invoice_path,
        month=month or _default_month(),
        amount_override=amount,
    )
    typer.echo(json.dumps(claim.model_dump(), indent=2, default=str))


@claim_app.command("list")
def list_claims(
    employee_id: str,
    month: str = typer.Option(None, "--month"),
):
    claims = claim_service.list_claims(employee_id=employee_id, month=month)
    typer.echo(json.dumps([claim.model_dump() for claim in claims], indent=2, default=str))


@payslip_app.command("generate")
def generate_payslip(
    employee_id: str,
    month: str = typer.Option(None, "--month"),
    worked_days: Optional[int] = typer.Option(None, "--worked-days"),
):
    payslip, pdf_path = payslip_service.generate_payslip(
        employee_id, month or _default_month(), worked_days
    )
    typer.echo(json.dumps({"payslip": payslip.model_dump(), "pdf_path": pdf_path}, indent=2, default=str))


@payslip_app.command("generate-all")
def generate_all(month: str = typer.Option(None, "--month")):
    for employee in employee_service.list_employees():
        payslip_service.generate_payslip(employee.id, month or _default_month())
    typer.echo("Payslips generated")


@payslip_app.command("send")
def send_payslip(
    employee_id: str,
    month: str = typer.Option(None, "--month"),
    worked_days: Optional[int] = typer.Option(None, "--worked-days"),
    pdf: Optional[Path] = typer.Option(
        None,
        "--pdf",
        path_type=Path,
        help="Path to existing PDF from payslip generate (skips regenerating)",
    ),
):
    pdf_path = str(pdf) if pdf else None
    payslip_data, path_sent = payslip_service.send_payslip(
        employee_id, month or _default_month(), worked_days, pdf_path=pdf_path
    )
    typer.echo(f"Payslip sent: {path_sent}")


@payslip_app.command("send-all")
def send_all(month: str = typer.Option(None, "--month")):
    for employee in employee_service.list_employees():
        payslip_service.send_payslip(employee.id, month or _default_month())
    typer.echo("Payslips sent")


@auth_app.command("setup-gmail")
def setup_gmail():
    email_service.setup_oauth()
    typer.echo("Gmail OAuth setup complete")


if __name__ == "__main__":
    app()
