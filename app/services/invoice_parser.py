from __future__ import annotations

import logging
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Tuple

from pypdf import PdfReader

from app.config import (
    EXTRACTION_ALERT_EMAIL,
    HYBRID_CONFIDENCE_THRESHOLD,
    MAX_OCR_PAGES_INVOICE,
    OLLAMA_TEXT_MODEL,
)
from app.models.claim_models import InvoiceExtractionResult
from app.services.hybrid_confidence import score_invoice_extraction
from app.services.ocr_service import OCRService, ocr_service
from app.services.ollama_service import OllamaService, ollama_service

logger = logging.getLogger(__name__)


INVOICE_EXTRACTION_PROMPT = """
You extract structured invoice fields from OCR text.
Return JSON only.

Schema:
{
  "invoice_id": "string or null",
  "total_amount": 0,
  "currency": "IDR or USD or null",
  "confidence": 0.0
}

Rules:
- Do not invent numbers.
- total_amount must be numeric.
- confidence must be 0.0-1.0.
"""


TOTAL_LINE_PATTERN = re.compile(
    r"(?im)(?:grand\s*total|total\s*(?:amount|payment|pembayaran|tagihan)?|"
    r"amount\s*due|jumlah\s*(?:tagihan|bayar))[^\dA-Za-z]{0,8}"
    r"(?P<currency>rp|idr|usd|\$)?\s*(?P<amount>[0-9][0-9\.,\s]{1,})"
)
CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?im)(?P<currency>rp|idr|usd|\$)\s*(?P<amount>[0-9][0-9\.,\s]{1,})"
)
GENERIC_AMOUNT_PATTERN = re.compile(r"\b[0-9]{1,3}(?:[.,][0-9]{3})+(?:[.,][0-9]{2})?\b")
INVOICE_ID_PATTERNS = [
    re.compile(
        r"(?im)(?:invoice|inv|receipt|transaction|trx)\s*"
        r"(?:no|number|id|#|:|-)?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{3,})"
    ),
    re.compile(r"(?im)\b([A-Za-z]{2,}[A-Za-z0-9\-_/]{3,})\b"),
]


class InvoiceAlertEmailService(Protocol):
    def send_email(self, recipient_email: str, subject: str, body: str) -> None:
        ...


def _normalize_invoice_id(invoice_id: str) -> str:
    invoice_id = (invoice_id or "").strip()
    if invoice_id.startswith("#"):
        invoice_id = invoice_id[1:]
    invoice_id = re.sub(r"[\s\-]+", "", invoice_id)
    return invoice_id


def _normalize_currency(raw_currency: Optional[str]) -> Optional[str]:
    if not raw_currency:
        return None
    normalized = raw_currency.strip().upper()
    if normalized in {"RP", "IDR"}:
        return "IDR"
    if normalized in {"$", "USD"}:
        return "USD"
    return None


def _parse_amount(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    value = str(raw).strip()
    if not value:
        return None
    value = re.sub(r"[^0-9,\.]", "", value)
    if not value:
        return None

    dot_count = value.count(".")
    comma_count = value.count(",")

    if dot_count > 0 and comma_count == 0:
        if dot_count > 1:
            value = value.replace(".", "")
        else:
            left, right = value.split(".")
            if len(right) == 3 and len(left) >= 1:
                value = left + right
    if value.count(",") > 0 and value.count(".") > 0:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "")
            value = value.replace(",", ".")
        else:
            value = value.replace(",", "")
    else:
        if comma_count == 1 and dot_count == 0:
            left, right = value.split(",")
            if len(right) == 3 and len(left) >= 1:
                value = left + right
            else:
                value = left + "." + right
        elif comma_count > 1 and dot_count == 0:
            value = value.replace(",", "")

    try:
        return float(value)
    except ValueError:
        return None


def _looks_like_invoice_id(value: str) -> bool:
    if len(value) < 5:
        return False
    return any(ch.isalpha() for ch in value) and any(ch.isdigit() for ch in value)


def _extract_invoice_id(text: str) -> Optional[str]:
    for pattern in INVOICE_ID_PATTERNS:
        for match in pattern.finditer(text):
            candidate = _normalize_invoice_id(match.group(1))
            if _looks_like_invoice_id(candidate):
                return candidate
    return None


def _extract_total_amount(text: str) -> Tuple[float, Optional[str]]:
    best_amount = 0.0
    best_currency: Optional[str] = None

    for match in TOTAL_LINE_PATTERN.finditer(text):
        amount = _parse_amount(match.group("amount"))
        if amount is None:
            continue
        if amount >= best_amount:
            best_amount = amount
            best_currency = _normalize_currency(match.group("currency"))

    if best_amount > 0:
        return best_amount, best_currency

    for match in CURRENCY_AMOUNT_PATTERN.finditer(text):
        amount = _parse_amount(match.group("amount"))
        if amount is None:
            continue
        if amount >= best_amount:
            best_amount = amount
            best_currency = _normalize_currency(match.group("currency"))

    if best_amount > 0:
        return best_amount, best_currency

    for match in GENERIC_AMOUNT_PATTERN.finditer(text):
        amount = _parse_amount(match.group(0))
        if amount is None:
            continue
        if amount >= best_amount:
            best_amount = amount

    return best_amount, best_currency


def _extract_invoice_fields_from_text(text: str) -> Dict[str, Any]:
    invoice_id = _extract_invoice_id(text)
    total_amount, currency = _extract_total_amount(text)
    confidence = score_invoice_extraction(total_amount, invoice_id, currency)
    return {
        "invoice_id": invoice_id,
        "total_amount": total_amount,
        "currency": currency,
        "confidence": confidence,
    }


class InvoiceParser:
    def __init__(
        self,
        ocr_service_instance: OCRService = ocr_service,
        ollama_service_instance: OllamaService = ollama_service,
        email_service_instance: Optional[InvoiceAlertEmailService] = None,
        text_model: str = OLLAMA_TEXT_MODEL,
        confidence_threshold: float = HYBRID_CONFIDENCE_THRESHOLD,
        max_ocr_pages: int = MAX_OCR_PAGES_INVOICE,
        alert_recipient: str = EXTRACTION_ALERT_EMAIL,
    ):
        if email_service_instance is None:
            from app.services.email_service import email_service

            email_service_instance = email_service

        self.ocr_service = ocr_service_instance
        self.ollama_service = ollama_service_instance
        self.email_service = email_service_instance
        self.text_model = text_model
        self.confidence_threshold = confidence_threshold
        self.max_ocr_pages = max_ocr_pages
        self.alert_recipient = alert_recipient

    def parse_invoice(self, file_path: Path) -> InvoiceExtractionResult:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"

        if mime_type == "application/pdf":
            return self._parse_pdf(file_path)
        return self._parse_image(file_path)

    def _parse_pdf(self, file_path: Path) -> InvoiceExtractionResult:
        embedded_text = self._extract_pdf_text(file_path)
        if embedded_text:
            rule_result = self._result_from_text(embedded_text)
            if self._is_confident(rule_result):
                return rule_result

        ocr_text = self.ocr_service.extract_text_from_pdf(
            file_path,
            max_pages=self.max_ocr_pages,
        )
        combined_text = "\n".join(
            part for part in [embedded_text, ocr_text] if part and part.strip()
        ).strip()

        if combined_text:
            ocr_rule_result = self._result_from_text(combined_text)
            if self._is_confident(ocr_rule_result):
                return ocr_rule_result

            llm_result = self._parse_with_text_llm(combined_text)
            if self._is_confident(llm_result):
                return llm_result

        detail = "Could not extract required invoice fields with local pipeline"
        self._send_failure_alert(file_path=file_path, detail=detail)
        raise ValueError(detail)

    def _parse_image(self, file_path: Path) -> InvoiceExtractionResult:
        ocr_text = self.ocr_service.extract_text_from_image(file_path)
        if ocr_text:
            rule_result = self._result_from_text(ocr_text)
            if self._is_confident(rule_result):
                return rule_result

            llm_result = self._parse_with_text_llm(ocr_text)
            if self._is_confident(llm_result):
                return llm_result

        detail = "Could not extract required invoice fields from image"
        self._send_failure_alert(file_path=file_path, detail=detail)
        raise ValueError(detail)

    @staticmethod
    def _extract_pdf_text(file_path: Path) -> str:
        reader = PdfReader(str(file_path))
        text_parts = []
        for page in reader.pages[:3]:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
        return "\n".join(text_parts).strip()

    @staticmethod
    def _result_from_text(text: str) -> InvoiceExtractionResult:
        extracted = _extract_invoice_fields_from_text(text)
        return InvoiceExtractionResult(
            invoice_id=extracted["invoice_id"],
            total_amount=extracted["total_amount"],
            currency=extracted["currency"],
            confidence=extracted["confidence"],
            raw={"source": "rules", "text_preview": text[:1200]},
        )

    def _parse_with_text_llm(self, text_content: str) -> InvoiceExtractionResult:
        prompt = (
            f"{INVOICE_EXTRACTION_PROMPT}\n\n"
            f"Invoice OCR text:\n{text_content[:16000]}"
        )
        raw_json = self.ollama_service.chat_json(
            prompt=prompt,
            system_prompt="You return strict JSON only.",
            model=self.text_model,
        )

        invoice_id = _normalize_invoice_id(str(raw_json.get("invoice_id") or ""))
        total_amount = _parse_amount(raw_json.get("total_amount")) or 0.0
        currency = _normalize_currency(
            str(raw_json.get("currency") or "") if raw_json.get("currency") else None
        )
        confidence = raw_json.get("confidence")
        try:
            confidence_f = float(confidence) if confidence is not None else None
        except (ValueError, TypeError):
            confidence_f = None

        if confidence_f is None:
            confidence_f = score_invoice_extraction(total_amount, invoice_id or None, currency)

        return InvoiceExtractionResult(
            invoice_id=invoice_id or None,
            total_amount=total_amount,
            currency=currency,
            confidence=confidence_f,
            raw=raw_json,
        )

    def _is_confident(self, result: InvoiceExtractionResult) -> bool:
        score = result.confidence
        if score is None:
            score = score_invoice_extraction(
                result.total_amount,
                result.invoice_id,
                result.currency,
            )
        return bool(result.total_amount > 0 and score >= self.confidence_threshold)

    def _send_failure_alert(self, file_path: Path, detail: str) -> None:
        if not self.alert_recipient:
            return

        subject = f"[HR Automation] Invoice extraction failed: {file_path.name}"
        body = (
            f"Invoice extraction failed after all local fallbacks.\n\n"
            f"File: {file_path}\n"
            f"Detail: {detail}\n"
            f"Time (UTC): {datetime.now(timezone.utc).isoformat()}\n"
        )
        try:
            self.email_service.send_email(self.alert_recipient, subject, body)
        except Exception as exc:
            logger.warning("Failed to send invoice extraction alert email: %s", exc)

invoice_parser = InvoiceParser()
