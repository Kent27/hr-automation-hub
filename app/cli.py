from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import typer

from app.automations.holiday_sync import holiday_sync_automation
from app.automations.registry import automation_runner
from app.automations.payslip import payslip_automation
from app.models.employee_models import Benefit, EmployeeCreate, EmployeeUpdate
from app.services.claim_service import claim_service
from app.services.employee_service import employee_service
from app.services.email_service import email_service
from app.services.payslip_service import payslip_service

app = typer.Typer(help="HR Automation Hub")
employee_app = typer.Typer(help="Manage employees")
claim_app = typer.Typer(help="Manage claims")
payslip_app = typer.Typer(help="Generate and send payslips")
holiday_app = typer.Typer(help="Manage public holidays")
automation_app = typer.Typer(help="Run registered automations")
auth_app = typer.Typer(help="Authentication helpers")

app.add_typer(employee_app, name="employee")
app.add_typer(claim_app, name="claim")
app.add_typer(payslip_app, name="payslip")
app.add_typer(holiday_app, name="holiday")
app.add_typer(automation_app, name="automation")
app.add_typer(auth_app, name="auth")


def _default_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _parse_run_date(value: Optional[str]) -> date:
    if not value:
        return datetime.utcnow().date()
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        raise typer.BadParameter("Date must be in YYYY-MM-DD format")


def _parse_benefits(values: Optional[List[str]]) -> List[Benefit]:
    benefits: List[Benefit] = []
    for raw in values or []:
        parts = [part.strip() for part in raw.split(":")]
        if len(parts) not in {2, 3}:
            raise typer.BadParameter(
                "Benefit must be in type:limit or type:limit:currency format"
            )

        benefit_type = parts[0]
        limit_str = parts[1]
        currency = parts[2] if len(parts) == 3 else "IDR"
        benefits.append(
            Benefit(
                type=benefit_type,
                limit=float(limit_str),
                currency=currency,
            )
        )
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
    month: Optional[str] = typer.Option(None, "--month"),
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
    month: Optional[str] = typer.Option(None, "--month"),
):
    claims = claim_service.list_claims(employee_id=employee_id, month=month)
    typer.echo(json.dumps([claim.model_dump() for claim in claims], indent=2, default=str))


@payslip_app.command("generate")
def generate_payslip(
    employee_id: str,
    month: Optional[str] = typer.Option(None, "--month"),
    worked_days: Optional[int] = typer.Option(None, "--worked-days"),
):
    payslip, pdf_path = payslip_service.generate_payslip(
        employee_id, month or _default_month(), worked_days
    )
    typer.echo(json.dumps({"payslip": payslip.model_dump(), "pdf_path": pdf_path}, indent=2, default=str))


@payslip_app.command("generate-all")
def generate_all(month: Optional[str] = typer.Option(None, "--month")):
    target_month = month or _default_month()
    payslip_automation.generate_all(target_month)
    typer.echo("Payslips generated")


@payslip_app.command("send")
def send_payslip(
    employee_id: str,
    month: Optional[str] = typer.Option(None, "--month"),
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
def send_all(month: Optional[str] = typer.Option(None, "--month")):
    target_month = month or _default_month()
    payslip_automation.send_all(target_month)
    typer.echo("Payslips sent")


@automation_app.command("list")
def list_automations():
    typer.echo(json.dumps(automation_runner.list_automations(), indent=2))


@automation_app.command("run-due")
def run_due(
    run_date: Optional[str] = typer.Option(
        None,
        "--date",
        help="Override run date in YYYY-MM-DD format",
    )
):
    target_date = _parse_run_date(run_date)
    results = [result.to_dict() for result in automation_runner.run_due(target_date)]
    typer.echo(json.dumps(results, indent=2))


@automation_app.command("run")
def run_automation(
    name: str,
    run_date: Optional[str] = typer.Option(
        None,
        "--date",
        help="Override run date in YYYY-MM-DD format",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Run even when automation is not due",
    ),
):
    target_date = _parse_run_date(run_date)
    try:
        result = automation_runner.run_one(name=name, run_date=target_date, force=force)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))
    typer.echo(json.dumps(result.to_dict(), indent=2))


@holiday_app.command("sync")
def sync_holidays(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the official government holiday PDF (e.g. Bank Indonesia calendar)",
    ),
):
    if not pdf_path.exists():
        typer.echo(f"File not found: {pdf_path}", err=True)
        raise typer.Exit(code=1)
    target_date = datetime.utcnow().date()
    result = holiday_sync_automation.run_with_pdf(pdf_path, target_date)
    typer.echo(json.dumps(result.to_dict(), indent=2))


@holiday_app.command("sync-auto")
def sync_holidays_auto(
    year: int = typer.Option(
        datetime.utcnow().year,
        "--year",
        min=2000,
        max=2100,
        help="Holiday calendar year to discover from trusted .go.id sources",
    ),
    seed_url: Optional[List[str]] = typer.Option(
        None,
        "--seed-url",
        help="Additional trusted seed URL to scan (can be passed multiple times)",
    ),
):
    from app.services.holiday_pdf_discovery_service import holiday_pdf_discovery_service

    try:
        discovery = holiday_pdf_discovery_service.discover_and_download(
            year=year,
            extra_seed_urls=seed_url,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    target_date = datetime.utcnow().date()
    sync_result = holiday_sync_automation.run_with_pdf(discovery.pdf_path, target_date)
    payload = {
        "discovery": discovery.to_dict(),
        "sync_result": sync_result.to_dict(),
    }
    typer.echo(json.dumps(payload, indent=2))


@holiday_app.command("list")
def list_holidays(
    year: Optional[int] = typer.Argument(None, help="Filter by year"),
):
    from app.utils.holidays import load_holiday_entries

    all_holidays = load_holiday_entries()
    if year:
        all_holidays = [h for h in all_holidays if h.holiday_date.year == year]
    for holiday in all_holidays:
        typer.echo(
            f"{holiday.holiday_date.isoformat()}  "
            f"{holiday.holiday_date.strftime('%A')}  {holiday.name}"
        )
    if not all_holidays:
        typer.echo("No holidays found")


@auth_app.command("setup-gmail")
def setup_gmail():
    email_service.setup_oauth()
    typer.echo("Gmail OAuth setup complete")


if __name__ == "__main__":
    app()
