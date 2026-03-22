from pathlib import Path

import pytest

from app.services.holiday_sync_service import (
    HOLIDAY_CATEGORY_CUTI_BERSAMA,
    HOLIDAY_CATEGORY_LIBUR_NASIONAL,
    HolidaySyncService,
    _extract_holidays_from_text,
)


class FakeOpenAIService:
    def __init__(self, text_payload=None, vision_payload=None):
        self.text_payload = text_payload or {"holidays": []}
        self.vision_payload = vision_payload or {"holidays": []}
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


class FakeEmailService:
    def __init__(self):
        self.sent = []

    def send_email(self, recipient_email: str, subject: str, body: str) -> None:
        self.sent.append((recipient_email, subject, body))


class EmptyTextHolidaySyncService(HolidaySyncService):
    @staticmethod
    def _extract_pdf_text(pdf_path: Path) -> str:
        return ""


class EmbeddedTextHolidaySyncService(HolidaySyncService):
    @staticmethod
    def _extract_pdf_text(pdf_path: Path) -> str:
        return "random noise"


class VisionReadyHolidaySyncService(EmbeddedTextHolidaySyncService):
    def _render_pdf_images_for_openai(self, pdf_path: Path):
        return ["data:image/png;base64,ZmFrZQ=="]


def test_extract_holidays_from_text_handles_indonesian_date_ranges():
    text = """
    Hari Libur Nasional
    20-21 Maret 2026: Hari Raya Idulfitri 1447 H
    Cuti Bersama
    22 Maret 2026: Cuti Bersama Idulfitri
    """

    holidays = _extract_holidays_from_text(text)

    assert holidays == [
        {
            "date": "2026-03-20",
            "name": "Hari Raya Idulfitri 1447 H",
            "category": HOLIDAY_CATEGORY_LIBUR_NASIONAL,
        },
        {
            "date": "2026-03-21",
            "name": "Hari Raya Idulfitri 1447 H",
            "category": HOLIDAY_CATEGORY_LIBUR_NASIONAL,
        },
        {
            "date": "2026-03-22",
            "name": "Cuti Bersama Idulfitri",
            "category": HOLIDAY_CATEGORY_CUTI_BERSAMA,
        },
    ]


def test_extract_holidays_from_pdf_uses_openai_text_fallback_when_needed(tmp_path: Path):
    pdf_file = tmp_path / "holidays.pdf"
    pdf_file.write_text("dummy", encoding="utf-8")

    text_payload = {
        "holidays": [
            {"date": "2026-08-17", "name": "Hari Kemerdekaan Republik Indonesia"},
            {"date": "2026-12-25", "name": "Hari Raya Natal"},
        ]
    }
    openai_service = FakeOpenAIService(text_payload=text_payload)
    service = EmbeddedTextHolidaySyncService(
        openai_service_instance=openai_service,
        email_service_instance=FakeEmailService(),
        openai_fallback_enabled=False,
    )

    holidays = service.extract_holidays_from_pdf(pdf_file)

    assert holidays == [
        {
            "date": "2026-08-17",
            "name": "Hari Kemerdekaan Republik Indonesia",
            "category": HOLIDAY_CATEGORY_LIBUR_NASIONAL,
        },
        {
            "date": "2026-12-25",
            "name": "Hari Raya Natal",
            "category": HOLIDAY_CATEGORY_LIBUR_NASIONAL,
        },
    ]
    assert openai_service.text_calls == 1
    assert openai_service.vision_calls == 0


def test_extract_holidays_from_pdf_prefers_openai_vision_when_confident(tmp_path: Path):
    pdf_file = tmp_path / "holidays.pdf"
    pdf_file.write_text("dummy", encoding="utf-8")

    vision_payload = {
        "holidays": [
            {"date": "2026-01-01", "name": "Tahun Baru Masehi"},
            {"date": "2026-02-17", "name": "Tahun Baru Imlek 2577 Kongzili"},
            {"date": "2026-03-21", "name": "Idul Fitri 1447 Hijriah"},
        ]
    }
    text_payload = {
        "holidays": [
            {"date": "2026-08-17", "name": "Hari Kemerdekaan Republik Indonesia"},
            {"date": "2026-12-25", "name": "Hari Raya Natal"},
        ]
    }
    openai_service = FakeOpenAIService(text_payload=text_payload, vision_payload=vision_payload)

    service = VisionReadyHolidaySyncService(
        openai_service_instance=openai_service,
        openai_fallback_enabled=True,
        email_service_instance=FakeEmailService(),
    )

    holidays = service.extract_holidays_from_pdf(pdf_file)

    assert holidays == [
        {
            "date": "2026-01-01",
            "name": "Tahun Baru Masehi",
            "category": HOLIDAY_CATEGORY_LIBUR_NASIONAL,
        },
        {
            "date": "2026-02-17",
            "name": "Tahun Baru Imlek 2577 Kongzili",
            "category": HOLIDAY_CATEGORY_LIBUR_NASIONAL,
        },
        {
            "date": "2026-03-21",
            "name": "Idul Fitri 1447 Hijriah",
            "category": HOLIDAY_CATEGORY_LIBUR_NASIONAL,
        },
    ]
    assert openai_service.vision_calls == 1
    assert openai_service.text_calls == 0


def test_extract_holidays_from_pdf_sends_alert_on_final_failure(tmp_path: Path):
    pdf_file = tmp_path / "holidays.pdf"
    pdf_file.write_text("dummy", encoding="utf-8")

    email_service = FakeEmailService()
    service = EmptyTextHolidaySyncService(
        openai_service_instance=FakeOpenAIService(),
        email_service_instance=email_service,
        openai_fallback_enabled=False,
        alert_recipient="kentkent2797@gmail.com",
    )

    with pytest.raises(ValueError, match="Could not extract holidays"):
        service.extract_holidays_from_pdf(pdf_file)

    assert len(email_service.sent) == 1
    assert email_service.sent[0][0] == "kentkent2797@gmail.com"
