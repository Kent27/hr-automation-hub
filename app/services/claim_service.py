from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from app.config import CLAIMS_DIR, CLAIMS_FILE
from app.models.claim_models import Claim, InvoiceExtractionResult
from app.models.employee_models import Benefit
from app.services.employee_service import EmployeeService, employee_service
from app.services.exchange_rate_service import (
    ExchangeRateService,
    exchange_rate_service,
)
from app.services.invoice_parser import InvoiceParser, invoice_parser
from app.services.storage_utils import read_json_list, write_json_list


def _normalize_month(month: Optional[str]) -> str:
    if month:
        try:
            datetime.strptime(month, "%Y-%m")
            return month
        except ValueError:
            raise ValueError("Month must be in YYYY-MM format")
    return datetime.utcnow().strftime("%Y-%m")


class ClaimService:
    def __init__(
        self,
        claims_path: Path = CLAIMS_FILE,
        claims_dir: Path = CLAIMS_DIR,
        employee_service_instance: EmployeeService = employee_service,
        invoice_parser_instance: InvoiceParser = invoice_parser,
        exchange_rate_service_instance: ExchangeRateService = exchange_rate_service,
    ):
        self.claims_path = claims_path
        self.claims_dir = claims_dir
        self.employee_service = employee_service_instance
        self.invoice_parser = invoice_parser_instance
        self.exchange_rate_service = exchange_rate_service_instance

    def list_claims(self, employee_id: Optional[str] = None, month: Optional[str] = None) -> List[Claim]:
        data = read_json_list(self.claims_path)
        claims = [Claim.model_validate(item) for item in data]
        if employee_id:
            claims = [claim for claim in claims if claim.employee_id == employee_id]
        if month:
            claims = [claim for claim in claims if claim.month == month]
        return claims

    def add_claim(
        self,
        employee_id: str,
        benefit_type: str,
        invoice_path: Path,
        month: Optional[str] = None,
        amount_override: Optional[float] = None,
    ) -> Claim:
        month_value = _normalize_month(month)
        employee = self.employee_service.get_employee(employee_id)
        if not employee:
            raise ValueError("Employee not found")

        benefit = next((b for b in employee.benefits if b.type == benefit_type), None)
        if not benefit:
            raise ValueError("Benefit type not found for employee")

        if amount_override is None:
            extraction = self.invoice_parser.parse_invoice(invoice_path)
            extraction = self._normalize_claim_currency(
                extraction,
                benefit_currency=benefit.currency,
            )
            amount_raw = extraction.total_amount
        else:
            extraction = InvoiceExtractionResult(
                total_amount=amount_override,
                currency="IDR",
                raw={"source": "amount_override"},
            )
            amount_raw = amount_override

        claims_for_month = self.list_claims(employee_id=employee_id, month=month_value)
        claims_for_benefit = [
            claim for claim in claims_for_month if claim.benefit_type == benefit_type
        ]

        benefit_limit_idr = self._resolve_benefit_limit_idr(
            benefit=benefit,
            existing_claims=claims_for_benefit,
        )

        already_approved = sum(claim.amount_approved for claim in claims_for_benefit)
        remaining = max(benefit_limit_idr - already_approved, 0)
        amount_approved = min(amount_raw, remaining)

        claim_id = str(uuid4())
        self.claims_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self.claims_dir / f"{claim_id}-{invoice_path.name}"
        shutil.copy2(invoice_path, stored_path)

        new_claim = Claim(
            id=claim_id,
            employee_id=employee_id,
            benefit_type=benefit_type,
            month=month_value,
            amount_raw=amount_raw,
            amount_approved=amount_approved,
            benefit_limit=benefit_limit_idr,
            invoice_id=extraction.invoice_id,
            invoice_path=str(stored_path),
            currency=extraction.currency,
            extraction=extraction,
            created_at=datetime.utcnow(),
        )

        all_claims = self.list_claims()
        all_claims.append(new_claim)
        write_json_list(self.claims_path, [claim.model_dump() for claim in all_claims])
        return new_claim

    def _resolve_benefit_limit_idr(
        self,
        benefit: Benefit,
        existing_claims: List[Claim],
    ) -> float:
        if existing_claims:
            existing_limit = existing_claims[0].benefit_limit
            if existing_limit >= 0:
                return existing_limit

        benefit_currency = (benefit.currency or "IDR").upper()
        if benefit_currency == "IDR":
            return benefit.limit

        if benefit_currency == "USD":
            try:
                quote = self.exchange_rate_service.get_usd_to_idr_quote()
            except Exception as exc:
                raise ValueError(
                    "Failed to fetch USD to IDR exchange rate for benefit limit. "
                    "Please retry or provide --amount in IDR."
                ) from exc
            return round(benefit.limit * quote.rate, 2)

        raise ValueError(
            f"Unsupported benefit currency: {benefit_currency}. "
            "Only IDR and USD are supported."
        )

    def _normalize_claim_currency(
        self,
        extraction: InvoiceExtractionResult,
        benefit_currency: str,
    ) -> InvoiceExtractionResult:
        currency = (extraction.currency or "").upper()
        if currency == "IDR":
            return extraction.model_copy(update={"currency": "IDR"})
        if currency == "USD":
            return self._convert_usd_extraction_to_idr(extraction)

        if currency:
            return extraction.model_copy(update={"currency": currency})

        if benefit_currency.upper() == "USD":
            return self._convert_usd_extraction_to_idr(extraction, assumed_from_benefit=True)

        return extraction

    def _convert_usd_extraction_to_idr(
        self,
        extraction: InvoiceExtractionResult,
        assumed_from_benefit: bool = False,
    ) -> InvoiceExtractionResult:
        if extraction.total_amount <= 0:
            return extraction

        try:
            quote = self.exchange_rate_service.get_usd_to_idr_quote()
        except Exception as exc:
            raise ValueError(
                "Failed to fetch USD to IDR exchange rate. "
                "Please retry or provide --amount in IDR."
            ) from exc

        converted_total = round(extraction.total_amount * quote.rate, 2)
        raw = dict(extraction.raw or {})
        raw.update(
            {
                "original_total_amount": extraction.total_amount,
                "original_currency": "USD",
                "fx_rate_usd_to_idr": quote.rate,
                "fx_provider": quote.provider,
                "fx_as_of": quote.as_of,
                "fx_source_url": quote.source_url,
                "converted_total_amount_idr": converted_total,
            }
        )
        if assumed_from_benefit:
            raw["currency_assumed_from_benefit"] = True

        return extraction.model_copy(
            update={
                "total_amount": converted_total,
                "currency": "IDR",
                "raw": raw,
            }
        )


claim_service = ClaimService()
