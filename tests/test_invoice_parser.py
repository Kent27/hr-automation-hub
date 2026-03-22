from pathlib import Path

import pytest

from app.services.invoice_parser import InvoiceParser, _normalize_invoice_id, _parse_amount


class FakeOpenAIService:
    def __init__(self, text_payload=None, vision_payload=None):
        self.text_payload = text_payload or {}
        self.vision_payload = vision_payload or {}
        self.text_calls = 0
        self.vision_calls = 0

    def chat_json(self, prompt: str, system_prompt: str, model: str):
        self.text_calls += 1
        return self.text_payload

    def chat_json_with_images(
        self,
        prompt: str,
        image_data_urls,
        system_prompt: str,
        model: str,
        image_detail: str = "high",
    ):
        self.vision_calls += 1
        return self.vision_payload


class StubPdfInvoiceParser(InvoiceParser):
    def __init__(
        self,
        embedded_text: str,
        rendered_images,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._embedded_text = embedded_text
        self._rendered_images = list(rendered_images)

    def _extract_pdf_text(self, file_path: Path) -> str:
        return self._embedded_text

    def _render_pdf_images(self, file_path: Path):
        return list(self._rendered_images)


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


def test_parse_invoice_pdf_calls_openai_text_when_embedded_text_exists(tmp_path: Path):
    invoice_file = tmp_path / "invoice.pdf"
    invoice_file.write_text("dummy", encoding="utf-8")

    openai_service = FakeOpenAIService(
        text_payload={
            "invoice_id": "INV-999",
            "total_amount": 999,
            "currency": "IDR",
            "confidence": 0.99,
        },
        vision_payload={
            "invoice_id": "INV-888",
            "total_amount": 888,
            "currency": "IDR",
            "confidence": 0.99,
        },
    )

    parser = StubPdfInvoiceParser(
        embedded_text="Invoice No: INV-123\nGrand Total: Rp 50.000",
        rendered_images=["data:image/png;base64,ZmFrZQ=="],
        openai_service_instance=openai_service,
        email_service_instance=FakeEmailService(),
    )

    result = parser.parse_invoice(invoice_file)

    assert result.invoice_id == "INV999"
    assert result.total_amount == 999.0
    assert result.currency == "IDR"
    assert openai_service.text_calls == 1
    assert openai_service.vision_calls == 0


def test_parse_invoice_pdf_openai_text_succeeds_without_vision(tmp_path: Path):
    invoice_file = tmp_path / "invoice.pdf"
    invoice_file.write_text("dummy", encoding="utf-8")

    openai_service = FakeOpenAIService(
        text_payload={
            "invoice_id": "INV-555",
            "total_amount": "125000",
            "currency": "IDR",
            "confidence": 0.95,
        },
        vision_payload={
            "invoice_id": "INV-777",
            "total_amount": "777000",
            "currency": "IDR",
            "confidence": 0.95,
        },
    )

    parser = StubPdfInvoiceParser(
        embedded_text="bad text",
        rendered_images=["data:image/png;base64,ZmFrZQ=="],
        openai_service_instance=openai_service,
        email_service_instance=FakeEmailService(),
    )

    result = parser.parse_invoice(invoice_file)

    assert result.invoice_id == "INV555"
    assert result.total_amount == 125000.0
    assert result.currency == "IDR"
    assert openai_service.text_calls == 1
    assert openai_service.vision_calls == 0


def test_parse_invoice_image_uses_openai_vision(tmp_path: Path):
    invoice_file = tmp_path / "invoice.png"
    invoice_file.write_text("dummy", encoding="utf-8")

    openai_service = FakeOpenAIService(
        vision_payload={
            "invoice_id": "INV-001",
            "total_amount": "150000",
            "currency": "IDR",
            "confidence": 0.95,
        }
    )
    parser = InvoiceParser(
        openai_service_instance=openai_service,
        email_service_instance=FakeEmailService(),
    )

    result = parser.parse_invoice(invoice_file)

    assert result.invoice_id == "INV001"
    assert result.total_amount == 150000.0
    assert result.currency == "IDR"
    assert openai_service.vision_calls == 1


def test_parse_invoice_image_sends_alert_on_final_failure(tmp_path: Path):
    invoice_file = tmp_path / "invoice.png"
    invoice_file.write_text("dummy", encoding="utf-8")

    email_service = FakeEmailService()
    parser = InvoiceParser(
        openai_service_instance=FakeOpenAIService(vision_payload={}),
        email_service_instance=email_service,
        alert_recipient="kentkent2797@gmail.com",
    )

    with pytest.raises(ValueError, match="Could not extract required invoice fields"):
        parser.parse_invoice(invoice_file)

    assert len(email_service.sent) == 1
    assert email_service.sent[0][0] == "kentkent2797@gmail.com"
