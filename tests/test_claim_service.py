from pathlib import Path

import pytest

from app.models.claim_models import InvoiceExtractionResult
from app.models.employee_models import Benefit, EmployeeCreate
from app.services.claim_service import ClaimService
from app.services.employee_service import EmployeeService
from app.services.exchange_rate_service import ExchangeRateQuote


class FakeInvoiceParser:
    def __init__(self, extraction_result: InvoiceExtractionResult):
        self.extraction_result = extraction_result

    def parse_invoice(self, invoice_path: Path) -> InvoiceExtractionResult:
        return self.extraction_result


class FakeSequenceInvoiceParser:
    def __init__(self, extraction_results):
        self.extraction_results = list(extraction_results)

    def parse_invoice(self, invoice_path: Path) -> InvoiceExtractionResult:
        if not self.extraction_results:
            raise ValueError("no more fake extraction results")
        return self.extraction_results.pop(0)


class FakeExchangeRateService:
    def __init__(self, rate: float = 16000.0, should_fail: bool = False):
        self.rate = rate
        self.should_fail = should_fail

    def get_usd_to_idr_quote(self) -> ExchangeRateQuote:
        if self.should_fail:
            raise ValueError("exchange rate unavailable")
        return ExchangeRateQuote(
            rate=self.rate,
            provider="test-provider",
            as_of="Sun, 22 Mar 2026 00:02:31 +0000",
            source_url="https://open.er-api.com/v6/latest/USD",
        )


def test_claim_is_capped_by_benefit_limit(tmp_path: Path):
    employees_path = tmp_path / "employees.json"
    claims_path = tmp_path / "claims.json"
    claims_dir = tmp_path / "claims"

    employee_service = EmployeeService(employees_path)
    employee = employee_service.create_employee(
        EmployeeCreate(
            full_name="Eric Wiyanto",
            email="eric@example.com",
            salary=10000000,
            benefits=[Benefit(type="education", limit=100)],
        )
    )

    claim_service = ClaimService(
        claims_path=claims_path,
        claims_dir=claims_dir,
        employee_service_instance=employee_service,
    )

    invoice1 = tmp_path / "invoice1.txt"
    invoice1.write_text("dummy")
    claim1 = claim_service.add_claim(
        employee_id=employee.id,
        benefit_type="education",
        invoice_path=invoice1,
        month="2026-01",
        amount_override=60,
    )

    invoice2 = tmp_path / "invoice2.txt"
    invoice2.write_text("dummy")
    claim2 = claim_service.add_claim(
        employee_id=employee.id,
        benefit_type="education",
        invoice_path=invoice2,
        month="2026-01",
        amount_override=80,
    )

    assert claim1.amount_approved == 60
    assert claim2.amount_approved == 40


def test_usd_claim_is_auto_converted_to_idr(tmp_path: Path):
    employees_path = tmp_path / "employees.json"
    claims_path = tmp_path / "claims.json"
    claims_dir = tmp_path / "claims"

    employee_service = EmployeeService(employees_path)
    employee = employee_service.create_employee(
        EmployeeCreate(
            full_name="Eric Wiyanto",
            email="eric@example.com",
            salary=10000000,
            benefits=[Benefit(type="ai-tools", limit=500000)],
        )
    )

    fake_parser = FakeInvoiceParser(
        InvoiceExtractionResult(
            total_amount=20,
            currency="USD",
            raw={"source": "rules"},
        )
    )

    claim_service = ClaimService(
        claims_path=claims_path,
        claims_dir=claims_dir,
        employee_service_instance=employee_service,
        invoice_parser_instance=fake_parser,
        exchange_rate_service_instance=FakeExchangeRateService(rate=16000),
    )

    invoice = tmp_path / "invoice-usd.txt"
    invoice.write_text("dummy")
    claim = claim_service.add_claim(
        employee_id=employee.id,
        benefit_type="ai-tools",
        invoice_path=invoice,
        month="2026-03",
    )

    assert claim.amount_raw == 320000
    assert claim.amount_approved == 320000
    assert claim.currency == "IDR"
    assert claim.extraction is not None
    assert claim.extraction.raw is not None
    assert claim.extraction.raw["original_total_amount"] == 20
    assert claim.extraction.raw["fx_rate_usd_to_idr"] == 16000
    assert claim.extraction.raw["converted_total_amount_idr"] == 320000


def test_usd_claim_raises_when_exchange_rate_lookup_fails(tmp_path: Path):
    employees_path = tmp_path / "employees.json"
    claims_path = tmp_path / "claims.json"
    claims_dir = tmp_path / "claims"

    employee_service = EmployeeService(employees_path)
    employee = employee_service.create_employee(
        EmployeeCreate(
            full_name="Eric Wiyanto",
            email="eric@example.com",
            salary=10000000,
            benefits=[Benefit(type="ai-tools", limit=500000)],
        )
    )

    fake_parser = FakeInvoiceParser(
        InvoiceExtractionResult(
            total_amount=20,
            currency="USD",
        )
    )

    claim_service = ClaimService(
        claims_path=claims_path,
        claims_dir=claims_dir,
        employee_service_instance=employee_service,
        invoice_parser_instance=fake_parser,
        exchange_rate_service_instance=FakeExchangeRateService(should_fail=True),
    )

    invoice = tmp_path / "invoice-usd.txt"
    invoice.write_text("dummy")

    with pytest.raises(ValueError, match="USD to IDR exchange rate"):
        claim_service.add_claim(
            employee_id=employee.id,
            benefit_type="ai-tools",
            invoice_path=invoice,
            month="2026-03",
        )


def test_usd_benefit_limit_is_converted_and_used_for_monthly_cap(tmp_path: Path):
    employees_path = tmp_path / "employees.json"
    claims_path = tmp_path / "claims.json"
    claims_dir = tmp_path / "claims"

    employee_service = EmployeeService(employees_path)
    employee = employee_service.create_employee(
        EmployeeCreate(
            full_name="Eric Wiyanto",
            email="eric@example.com",
            salary=10000000,
            benefits=[Benefit(type="ai-tools", limit=20, currency="USD")],
        )
    )

    fake_parser = FakeSequenceInvoiceParser(
        [
            InvoiceExtractionResult(total_amount=20, currency="USD"),
            InvoiceExtractionResult(total_amount=5, currency="USD"),
        ]
    )

    claim_service = ClaimService(
        claims_path=claims_path,
        claims_dir=claims_dir,
        employee_service_instance=employee_service,
        invoice_parser_instance=fake_parser,
        exchange_rate_service_instance=FakeExchangeRateService(rate=16000),
    )

    invoice1 = tmp_path / "invoice-usd-1.txt"
    invoice1.write_text("dummy")
    claim1 = claim_service.add_claim(
        employee_id=employee.id,
        benefit_type="ai-tools",
        invoice_path=invoice1,
        month="2026-03",
    )

    invoice2 = tmp_path / "invoice-usd-2.txt"
    invoice2.write_text("dummy")
    claim2 = claim_service.add_claim(
        employee_id=employee.id,
        benefit_type="ai-tools",
        invoice_path=invoice2,
        month="2026-03",
    )

    assert claim1.benefit_limit == 320000
    assert claim1.amount_approved == 320000
    assert claim2.benefit_limit == 320000
    assert claim2.amount_approved == 0


def test_missing_currency_uses_usd_benefit_currency_for_conversion(tmp_path: Path):
    employees_path = tmp_path / "employees.json"
    claims_path = tmp_path / "claims.json"
    claims_dir = tmp_path / "claims"

    employee_service = EmployeeService(employees_path)
    employee = employee_service.create_employee(
        EmployeeCreate(
            full_name="Eric Wiyanto",
            email="eric@example.com",
            salary=10000000,
            benefits=[Benefit(type="ai-tools", limit=20, currency="USD")],
        )
    )

    fake_parser = FakeInvoiceParser(
        InvoiceExtractionResult(
            total_amount=20,
            currency=None,
            raw={"source": "rules"},
        )
    )

    claim_service = ClaimService(
        claims_path=claims_path,
        claims_dir=claims_dir,
        employee_service_instance=employee_service,
        invoice_parser_instance=fake_parser,
        exchange_rate_service_instance=FakeExchangeRateService(rate=16000),
    )

    invoice = tmp_path / "invoice-usd.txt"
    invoice.write_text("dummy")
    claim = claim_service.add_claim(
        employee_id=employee.id,
        benefit_type="ai-tools",
        invoice_path=invoice,
        month="2026-03",
    )

    assert claim.amount_raw == 320000
    assert claim.currency == "IDR"
    assert claim.extraction is not None
    assert claim.extraction.raw is not None
    assert claim.extraction.raw["currency_assumed_from_benefit"] is True
