import json
from datetime import date
from pathlib import Path
from typing import Dict, List

from app.automations.holiday_sync import HolidaySyncAutomation
from app.services.holiday_sync_service import HolidaySyncService


class FakeHolidaySyncService(HolidaySyncService):
    def __init__(self, holidays_file: Path):
        super().__init__(holidays_file=holidays_file)

    def extract_holidays_from_pdf(self, pdf_path: Path) -> List[Dict[str, str]]:
        return [
            {
                "date": "2026-01-01",
                "name": "Tahun Baru",
                "category": "libur_nasional",
            },
            {
                "date": "2026-08-17",
                "name": "Cuti Bersama Kemerdekaan",
                "category": "cuti_bersama",
            },
        ]


def test_should_run_is_always_false():
    automation = HolidaySyncAutomation.__new__(HolidaySyncAutomation)
    assert automation.should_run(date(2026, 2, 28)) is False
    assert automation.should_run(date(2026, 12, 31)) is False


def test_sync_writes_holidays_from_pdf(tmp_path: Path):
    holidays_file = tmp_path / "holidays_id.json"
    holidays_file.write_text('{}', encoding="utf-8")
    dummy_pdf = tmp_path / "holidays.pdf"
    dummy_pdf.write_text("dummy")

    sync_service = FakeHolidaySyncService(holidays_file)
    automation = HolidaySyncAutomation(
        sync_service=sync_service,
    )

    result = automation.run_with_pdf(dummy_pdf, date(2026, 1, 15))

    assert result.ran is True
    assert result.processed_count == 2

    data = json.loads(holidays_file.read_text(encoding="utf-8"))
    assert "2026" in data
    assert len(data["2026"]["libur_nasional"]) == 1
    assert len(data["2026"]["cuti_bersama"]) == 1
    assert data["2026"]["libur_nasional"][0] == {
        "date": "2026-01-01",
        "name": "Tahun Baru",
    }
    assert data["2026"]["cuti_bersama"][0] == {
        "date": "2026-08-17",
        "name": "Cuti Bersama Kemerdekaan",
    }


def test_sync_preserves_existing_years(tmp_path: Path):
    holidays_file = tmp_path / "holidays_id.json"
    holidays_file.write_text(
        json.dumps(
            {
                "2025": {
                    "libur_nasional": [
                        {
                            "date": "2025-01-01",
                            "name": "Tahun Baru Masehi",
                        }
                    ],
                    "cuti_bersama": [],
                }
            }
        ),
        encoding="utf-8",
    )
    dummy_pdf = tmp_path / "holidays.pdf"
    dummy_pdf.write_text("dummy")

    sync_service = FakeHolidaySyncService(holidays_file)
    automation = HolidaySyncAutomation(
        sync_service=sync_service,
    )

    automation.run_with_pdf(dummy_pdf, date(2026, 1, 15))

    data = json.loads(holidays_file.read_text(encoding="utf-8"))
    assert "2025" in data
    assert "2026" in data
    assert data["2025"]["libur_nasional"] == [
        {
            "date": "2025-01-01",
            "name": "Tahun Baru Masehi",
        }
    ]
    assert data["2025"]["cuti_bersama"] == []
