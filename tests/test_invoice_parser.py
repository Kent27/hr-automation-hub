from pathlib import Path

import pytest

from app.services.invoice_parser import InvoiceParser, _normalize_invoice_id, _parse_amount


class FakeOCRService:
    def __init__(self, image_text: str = "", pdf_text: str = ""):
        self.image_text = image_text
        self.pdf_text = pdf_text

    def extract_text_from_image(self, image_path: Path) -> str:
        return self.image_text

    def extract_text_from_pdf(self, pdf_path: Path, max_pages: int) -> str:
        return self.pdf_text


class FakeOllamaService:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def chat_json(self, prompt: str, system_prompt: str, model: str):
        self.calls += 1
        return self.payload


class FakeEmailService:
    def __init__(self):
        self.sent = []

    def send_email(self, recipient_email: str, subject: str, body: str) -> None:
        self.sent.append((recipient_email, subject, body))


def test_normalize_invoice_id_strips_hash_and_spaces():
    assert _normalize_invoice_id(" # INV 123 ") == "INV123"


def test_parse_amount_handles_common_formats():
    assert _parse_amount("Rp 50.000") == 50000.0
    assert _parse_amount("50,000") == 50000.0
    assert _parse_amount("1.234,56") == 1234.56
    assert _parse_amount("1,234.56") == 1234.56


def test_parse_invoice_image_uses_rules_before_llm(tmp_path: Path):
    invoice_file = tmp_path / "invoice.png"
    invoice_file.write_text("dummy", encoding="utf-8")

    parser = InvoiceParser(
        ocr_service_instance=FakeOCRService(
            image_text="Invoice No: INV-123\nGrand Total: Rp 50.000"
        ),
        ollama_service_instance=FakeOllamaService(
            {
                "invoice_id": "INV-999",
                "total_amount": 999,
                "currency": "IDR",
                "confidence": 0.99,
            }
        ),
        email_service_instance=FakeEmailService(),
    )

    result = parser.parse_invoice(invoice_file)

    assert result.invoice_id == "INV123"
    assert result.total_amount == 50000.0
    assert result.currency == "IDR"
    assert parser.ollama_service.calls == 0


def test_parse_invoice_image_uses_llm_fallback_when_rules_fail(tmp_path: Path):
    invoice_file = tmp_path / "invoice.png"
    invoice_file.write_text("dummy", encoding="utf-8")

    ollama_service = FakeOllamaService(
        {
            "invoice_id": "INV-555",
            "total_amount": "125000",
            "currency": "IDR",
            "confidence": 0.95,
        }
    )
    parser = InvoiceParser(
        ocr_service_instance=FakeOCRService(image_text="bad ocr text"),
        ollama_service_instance=ollama_service,
        email_service_instance=FakeEmailService(),
    )

    result = parser.parse_invoice(invoice_file)

    assert result.invoice_id == "INV555"
    assert result.total_amount == 125000.0
    assert result.currency == "IDR"
    assert ollama_service.calls == 1


def test_parse_invoice_image_sends_alert_on_final_failure(tmp_path: Path):
    invoice_file = tmp_path / "invoice.png"
    invoice_file.write_text("dummy", encoding="utf-8")

    email_service = FakeEmailService()
    parser = InvoiceParser(
        ocr_service_instance=FakeOCRService(image_text=""),
        ollama_service_instance=FakeOllamaService({}),
        email_service_instance=email_service,
        alert_recipient="kentkent2797@gmail.com",
    )

    with pytest.raises(ValueError, match="Could not extract required invoice fields"):
        parser.parse_invoice(invoice_file)

    assert len(email_service.sent) == 1
    assert email_service.sent[0][0] == "kentkent2797@gmail.com"
