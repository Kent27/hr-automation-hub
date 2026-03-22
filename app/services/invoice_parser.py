from __future__ import annotations

import base64
import logging
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from pypdf import PdfReader

from app.config import (
    EXTRACTION_ALERT_EMAIL,
    HYBRID_CONFIDENCE_THRESHOLD,
    OPENAI_INVOICE_IMAGE_DPI,
    OPENAI_INVOICE_MAX_PAGES,
    OPENAI_MODEL,
)
from app.models.claim_models import InvoiceExtractionResult
from app.services.hybrid_confidence import score_invoice_extraction
from app.services.openai_json_service import OpenAIJsonService, openai_json_service

logger = logging.getLogger(__name__)


INVOICE_EXTRACTION_TEXT_PROMPT = """
You extract structured invoice fields from invoice text.
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

INVOICE_EXTRACTION_VISION_PROMPT = """
You extract structured invoice fields from invoice image(s).
Return JSON only.

Schema:
{
  "invoice_id": "string or null",
  "total_amount": 0,
  "currency": "IDR or USD or null",
  "confidence": 0.0
}

Rules:
- Read totals and currency from the visible invoice.
- Do not invent values.
- total_amount must be numeric.
- confidence must be 0.0-1.0.
"""


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


class InvoiceParser:
    def __init__(
        self,
        openai_service_instance: Optional[OpenAIJsonService] = None,
        email_service_instance: Optional[InvoiceAlertEmailService] = None,
        openai_model: str = OPENAI_MODEL,
        openai_max_pages: int = OPENAI_INVOICE_MAX_PAGES,
        openai_image_dpi: int = OPENAI_INVOICE_IMAGE_DPI,
        confidence_threshold: float = HYBRID_CONFIDENCE_THRESHOLD,
        alert_recipient: str = EXTRACTION_ALERT_EMAIL,
    ):
        if email_service_instance is None:
            from app.services.email_service import email_service

            email_service_instance = email_service

        if openai_service_instance is None:
            openai_service_instance = openai_json_service

        self.openai_service = openai_service_instance
        self.email_service = email_service_instance
        self.openai_model = openai_model
        self.openai_max_pages = max(1, openai_max_pages)
        self.openai_image_dpi = max(96, openai_image_dpi)
        self.confidence_threshold = confidence_threshold
        self.alert_recipient = alert_recipient

    def parse_invoice(self, file_path: Path) -> InvoiceExtractionResult:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"

        if mime_type == "application/pdf":
            return self._parse_pdf(file_path)
        return self._parse_image(file_path)

    def _parse_pdf(self, file_path: Path) -> InvoiceExtractionResult:
        openai_errors: List[str] = []
        embedded_text = self._extract_pdf_text(file_path)
        if embedded_text:
            try:
                openai_text_result = self._parse_with_openai_text(embedded_text)
                if self._is_confident(openai_text_result):
                    return openai_text_result
            except Exception as exc:
                openai_errors.append(str(exc))

        try:
            openai_vision_result = self._parse_with_openai_vision_pdf(file_path)
            if self._is_confident(openai_vision_result):
                return openai_vision_result
        except Exception as exc:
            openai_errors.append(str(exc))

        detail = "Could not extract required invoice fields with OpenAI pipeline"
        if openai_errors:
            detail = f"{detail}. Last error: {openai_errors[-1]}"
        self._send_failure_alert(file_path=file_path, detail=detail)
        raise ValueError(detail)

    def _parse_image(self, file_path: Path) -> InvoiceExtractionResult:
        try:
            openai_vision_result = self._parse_with_openai_vision_image(file_path)
        except Exception as exc:
            detail = f"Could not extract required invoice fields from image. Last error: {exc}"
            self._send_failure_alert(file_path=file_path, detail=detail)
            raise ValueError(detail) from exc

        if self._is_confident(openai_vision_result):
            return openai_vision_result

        detail = "Could not extract required invoice fields from image with OpenAI vision"
        self._send_failure_alert(file_path=file_path, detail=detail)
        raise ValueError(detail)

    def _extract_pdf_text(self, file_path: Path) -> str:
        reader = PdfReader(str(file_path))
        text_parts = []
        for page in reader.pages[: self.openai_max_pages]:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
        return "\n".join(text_parts).strip()

    def _parse_with_openai_text(self, text_content: str) -> InvoiceExtractionResult:
        prompt = (
            f"{INVOICE_EXTRACTION_TEXT_PROMPT}\n\n"
            f"Invoice text:\n{text_content[:20000]}"
        )
        raw_json = self.openai_service.chat_json(
            prompt=prompt,
            system_prompt="You return strict JSON only.",
            model=self.openai_model,
        )
        return self._result_from_llm_payload(raw_json, source="openai_text")

    def _parse_with_openai_vision_pdf(self, file_path: Path) -> InvoiceExtractionResult:
        image_data_urls = self._render_pdf_images(file_path)
        if not image_data_urls:
            raise ValueError("No PDF pages were rendered for vision extraction")
        raw_json = self.openai_service.chat_json_with_images(
            prompt=INVOICE_EXTRACTION_VISION_PROMPT,
            image_data_urls=image_data_urls,
            system_prompt="You return strict JSON only.",
            model=self.openai_model,
        )
        return self._result_from_llm_payload(raw_json, source="openai_vision_pdf")

    def _parse_with_openai_vision_image(self, file_path: Path) -> InvoiceExtractionResult:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "image/png"
        image_data_url = (
            f"data:{mime_type};base64,"
            + base64.b64encode(file_path.read_bytes()).decode("ascii")
        )
        raw_json = self.openai_service.chat_json_with_images(
            prompt=INVOICE_EXTRACTION_VISION_PROMPT,
            image_data_urls=[image_data_url],
            system_prompt="You return strict JSON only.",
            model=self.openai_model,
        )
        return self._result_from_llm_payload(raw_json, source="openai_vision_image")

    def _render_pdf_images(self, file_path: Path) -> List[str]:
        try:
            import fitz
        except ImportError as exc:
            raise ValueError("PyMuPDF is not installed. Install pymupdf first.") from exc

        image_data_urls: List[str] = []
        with fitz.open(str(file_path)) as document:
            pages_to_read = min(self.openai_max_pages, document.page_count)
            zoom = self.openai_image_dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            for page_index in range(pages_to_read):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                png_bytes = pixmap.tobytes("png")
                image_data_urls.append(
                    "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
                )

        return image_data_urls

    def _result_from_llm_payload(
        self,
        raw_json: Dict[str, Any],
        source: str,
    ) -> InvoiceExtractionResult:
        payload = dict(raw_json or {})

        invoice_id = _normalize_invoice_id(str(payload.get("invoice_id") or ""))
        total_amount = _parse_amount(payload.get("total_amount")) or 0.0
        currency = _normalize_currency(
            str(payload.get("currency") or "") if payload.get("currency") else None
        )
        confidence = payload.get("confidence")
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
            raw={"source": source, **payload},
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
            f"Invoice extraction failed after OpenAI extraction fallback(s).\n\n"
            f"File: {file_path}\n"
            f"Detail: {detail}\n"
            f"Time (UTC): {datetime.now(timezone.utc).isoformat()}\n"
        )
        try:
            self.email_service.send_email(self.alert_recipient, subject, body)
        except Exception as exc:
            logger.warning("Failed to send invoice extraction alert email: %s", exc)

invoice_parser = InvoiceParser()
