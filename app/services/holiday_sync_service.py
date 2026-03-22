from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Set

from pypdf import PdfReader

from app.config import (
    EXTRACTION_ALERT_EMAIL,
    HOLIDAY_MIN_CONFIDENT_ENTRIES,
    HOLIDAYS_FILE,
    HYBRID_CONFIDENCE_THRESHOLD,
    OPENAI_API_KEY,
    OPENAI_HOLIDAY_FALLBACK_ENABLED,
    OPENAI_HOLIDAY_IMAGE_DPI,
    OPENAI_HOLIDAY_MAX_PAGES,
    OPENAI_MODEL,
    OLLAMA_TEXT_MODEL,
)
from app.services.hybrid_confidence import score_holiday_entries
from app.services.openai_json_service import OpenAIJsonService, openai_json_service
from app.services.ollama_service import OllamaService, ollama_service

logger = logging.getLogger(__name__)

HOLIDAY_CATEGORY_LIBUR_NASIONAL = "libur_nasional"
HOLIDAY_CATEGORY_CUTI_BERSAMA = "cuti_bersama"
HOLIDAY_CATEGORIES = (
    HOLIDAY_CATEGORY_LIBUR_NASIONAL,
    HOLIDAY_CATEGORY_CUTI_BERSAMA,
)
HOLIDAY_CATEGORY_LABELS = {
    HOLIDAY_CATEGORY_LIBUR_NASIONAL: "Hari Libur Nasional",
    HOLIDAY_CATEGORY_CUTI_BERSAMA: "Cuti Bersama",
}

HOLIDAY_EXTRACTION_PROMPT = """
Extract Indonesian public holiday dates and names from text.
Return JSON only.

Schema:
{
  "holidays": [
    {
      "date": "YYYY-MM-DD",
      "name": "Holiday name in Indonesian",
      "category": "libur_nasional or cuti_bersama"
    }
  ]
}

Rules:
- Use ISO date format (YYYY-MM-DD).
- Include both Hari Libur Nasional and Cuti Bersama.
- If a date range appears (e.g. 20-21 Maret 2026), include each date separately.
- Do not include non-holiday dates.
"""

HOLIDAY_EXTRACTION_VISION_PROMPT = """
Extract Indonesian public holiday dates and names from the attached document page images.
Return JSON only.

Schema:
{
  "holidays": [
    {
      "date": "YYYY-MM-DD",
      "name": "Holiday name in Indonesian",
      "category": "libur_nasional or cuti_bersama"
    }
  ]
}

Rules:
- Only extract rows from the holiday appendix tables (A. Hari Libur Nasional, B. Cuti Bersama).
- Ignore signature/issued dates like "Ditetapkan ... 19 September 2025".
- Expand date ranges (e.g. 21-22 Maret) into separate dates.
- Expand comma/list dates (e.g. 20, 23, dan 24 Maret) into separate dates.
- If row omits year, infer it from the table year heading.
- category must be exactly libur_nasional or cuti_bersama.
"""


MONTH_NAME_TO_NUMBER = {
    "januari": 1,
    "january": 1,
    "februari": 2,
    "february": 2,
    "maret": 3,
    "march": 3,
    "april": 4,
    "mei": 5,
    "may": 5,
    "juni": 6,
    "june": 6,
    "juli": 7,
    "july": 7,
    "agustus": 8,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "october": 10,
    "november": 11,
    "desember": 12,
    "december": 12,
}

RANGE_DATE_PATTERN = re.compile(
    r"(?P<start>\d{1,2})\s*(?:-|–|—|s/d|s\.d\.)\s*(?P<end>\d{1,2})\s+"
    r"(?P<month>[A-Za-z]+)\s+(?P<year>20\d{2})",
    re.IGNORECASE,
)
SINGLE_DATE_PATTERN = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>20\d{2})",
    re.IGNORECASE,
)


class HolidaySyncAlertEmailService(Protocol):
    def send_email(self, recipient_email: str, subject: str, body: str) -> None:
        ...


def _normalize_category(raw_category: Optional[str], name_hint: str = "") -> str:
    candidates = [raw_category or "", name_hint]
    for value in candidates:
        lowered = value.strip().lower()
        if not lowered:
            continue
        if "cuti" in lowered:
            return HOLIDAY_CATEGORY_CUTI_BERSAMA
        if "libur nasional" in lowered or "hari libur" in lowered or "nasional" in lowered:
            return HOLIDAY_CATEGORY_LIBUR_NASIONAL
    return HOLIDAY_CATEGORY_LIBUR_NASIONAL


def _month_number(raw_value: str) -> Optional[int]:
    return MONTH_NAME_TO_NUMBER.get(raw_value.strip().lower())


def _clean_holiday_name(value: str, fallback: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"^[-–—:.\s]+", "", cleaned)
    cleaned = re.sub(r"^\d+[\).\-]\s*", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned or fallback


def _extract_name_from_line(line: str, date_match_end: int, section_fallback: str) -> str:
    if ":" in line:
        right_side = line.split(":", 1)[1]
        return _clean_holiday_name(right_side, section_fallback)
    tail = line[date_match_end:]
    return _clean_holiday_name(tail, section_fallback)


def _dedupe_holidays(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    by_key: Dict[tuple[str, str], str] = {}
    for entry in entries:
        iso_date = str(entry.get("date") or "")
        name = str(entry.get("name") or "").strip() or "Unnamed Holiday"
        category = _normalize_category(
            str(entry.get("category") or ""),
            name_hint=name,
        )
        if not iso_date:
            continue
        key = (iso_date, category)
        existing = by_key.get(key)
        if not existing:
            by_key[key] = name
            continue
        if existing in {"Unnamed Holiday", "Hari Libur Nasional"} and name:
            by_key[key] = name

    return [
        {
            "date": iso_date,
            "name": by_key[(iso_date, category)],
            "category": category,
        }
        for iso_date, category in sorted(by_key.keys())
    ]


def _extract_holidays_from_text(text: str) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    current_category = HOLIDAY_CATEGORY_LIBUR_NASIONAL

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        lower_line = line.lower()

        if "cuti bersama" in lower_line:
            current_category = HOLIDAY_CATEGORY_CUTI_BERSAMA
        elif "hari libur nasional" in lower_line:
            current_category = HOLIDAY_CATEGORY_LIBUR_NASIONAL

        section_label = HOLIDAY_CATEGORY_LABELS[current_category]

        range_match = RANGE_DATE_PATTERN.search(line)
        if range_match:
            month = _month_number(range_match.group("month"))
            if month is None:
                continue
            year = int(range_match.group("year"))
            start_day = int(range_match.group("start"))
            end_day = int(range_match.group("end"))
            if start_day > end_day:
                start_day, end_day = end_day, start_day

            holiday_name = _extract_name_from_line(line, range_match.end(), section_label)
            for day in range(start_day, end_day + 1):
                try:
                    iso_date = date(year, month, day).isoformat()
                except ValueError:
                    continue
                entries.append(
                    {
                        "date": iso_date,
                        "name": holiday_name,
                        "category": current_category,
                    }
                )
            continue

        single_match = SINGLE_DATE_PATTERN.search(line)
        if not single_match:
            continue

        month = _month_number(single_match.group("month"))
        if month is None:
            continue
        year = int(single_match.group("year"))
        day = int(single_match.group("day"))
        try:
            iso_date = date(year, month, day).isoformat()
        except ValueError:
            continue

        holiday_name = _extract_name_from_line(line, single_match.end(), section_label)
        entries.append(
            {
                "date": iso_date,
                "name": holiday_name,
                "category": current_category,
            }
        )

    return _dedupe_holidays(entries)


class HolidaySyncService:
    def __init__(
        self,
        holidays_file: Path = HOLIDAYS_FILE,
        ollama_service_instance: OllamaService = ollama_service,
        openai_service_instance: Optional[OpenAIJsonService] = None,
        email_service_instance: Optional[HolidaySyncAlertEmailService] = None,
        text_model: str = OLLAMA_TEXT_MODEL,
        openai_model: str = OPENAI_MODEL,
        openai_fallback_enabled: bool = OPENAI_HOLIDAY_FALLBACK_ENABLED,
        openai_max_pages: int = OPENAI_HOLIDAY_MAX_PAGES,
        openai_image_dpi: int = OPENAI_HOLIDAY_IMAGE_DPI,
        confidence_threshold: float = HYBRID_CONFIDENCE_THRESHOLD,
        min_confident_entries: int = HOLIDAY_MIN_CONFIDENT_ENTRIES,
        alert_recipient: str = EXTRACTION_ALERT_EMAIL,
    ):
        if email_service_instance is None:
            from app.services.email_service import email_service

            email_service_instance = email_service

        self.holidays_file = holidays_file
        self.ollama_service = ollama_service_instance
        if openai_service_instance is None and openai_fallback_enabled and OPENAI_API_KEY:
            openai_service_instance = openai_json_service
        self.openai_service = openai_service_instance
        self.email_service = email_service_instance
        self.text_model = text_model
        self.openai_model = openai_model
        self.openai_fallback_enabled = bool(
            openai_fallback_enabled and self.openai_service is not None
        )
        self.openai_max_pages = max(1, openai_max_pages)
        self.openai_image_dpi = max(96, openai_image_dpi)
        self.confidence_threshold = confidence_threshold
        self.min_confident_entries = max(1, min_confident_entries)
        self.alert_recipient = alert_recipient

    def extract_holidays_from_pdf(self, pdf_path: Path) -> List[Dict[str, str]]:
        embedded_text = self._extract_pdf_text(pdf_path)

        openai_entries = self._extract_with_openai_vision_llm(pdf_path)
        if self._is_confident_enough(openai_entries):
            return openai_entries

        combined_text = (embedded_text or "").strip()

        if combined_text:
            llm_entries = self._extract_with_text_llm(combined_text)
            if self._is_confident_enough(llm_entries):
                return llm_entries

            if openai_entries and self._entry_score(openai_entries) > self._entry_score(llm_entries):
                return openai_entries

        detail = "Could not extract holidays with local Ollama pipeline"
        if self.openai_fallback_enabled:
            detail = "Could not extract holidays with OpenAI vision + local Ollama text pipeline"
        self._send_failure_alert(pdf_path, detail)
        raise ValueError(detail)

    def sync_from_pdf(self, pdf_path: Path) -> Set[date]:
        raw_holidays = self.extract_holidays_from_pdf(pdf_path)
        dates: Set[date] = set()
        years: Set[int] = set()
        entries_by_year: Dict[int, Dict[str, Dict[str, str]]] = {}
        for entry in raw_holidays:
            try:
                d = date.fromisoformat(entry["date"])
            except (KeyError, ValueError):
                continue

            raw_name = str(entry.get("name") or "").strip()
            category = _normalize_category(
                str(entry.get("category") or ""),
                name_hint=raw_name,
            )

            dates.add(d)
            years.add(d.year)

            year_entries = entries_by_year.setdefault(
                d.year,
                {
                    HOLIDAY_CATEGORY_LIBUR_NASIONAL: {},
                    HOLIDAY_CATEGORY_CUTI_BERSAMA: {},
                },
            )
            year_entries[category][d.isoformat()] = raw_name or "Unnamed Holiday"

        if not dates:
            raise ValueError("No valid holiday dates found in the PDF")

        existing = self._read_file()
        for year in years:
            year_entries = entries_by_year.get(
                year,
                {
                    HOLIDAY_CATEGORY_LIBUR_NASIONAL: {},
                    HOLIDAY_CATEGORY_CUTI_BERSAMA: {},
                },
            )

            existing[str(year)] = {
                category: [
                    {
                        "date": iso_date,
                        "name": year_entries[category][iso_date],
                    }
                    for iso_date in sorted(year_entries[category])
                ]
                for category in HOLIDAY_CATEGORIES
            }
        self._write_file(existing)

        logger.info("Synced %d holidays from PDF across years %s", len(dates), years)
        return dates

    @staticmethod
    def _extract_pdf_text(pdf_path: Path) -> str:
        reader = PdfReader(str(pdf_path))
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
        return "\n".join(text_parts).strip()

    def _extract_with_text_llm(self, text: str) -> List[Dict[str, str]]:
        prompt = f"{HOLIDAY_EXTRACTION_PROMPT}\n\nDocument text:\n{text[:20000]}"
        payload = self.ollama_service.chat_json(
            prompt=prompt,
            system_prompt="You return strict JSON only.",
            model=self.text_model,
        )
        return self._parse_holidays_payload(payload)

    def _extract_with_openai_vision_llm(self, pdf_path: Path) -> List[Dict[str, str]]:
        if not self.openai_fallback_enabled or self.openai_service is None:
            return []

        try:
            image_data_urls = self._render_pdf_images_for_openai(pdf_path)
        except Exception as exc:
            logger.warning("Failed to render PDF pages for OpenAI vision fallback: %s", exc)
            return []

        if not image_data_urls:
            return []

        try:
            payload = self.openai_service.chat_json_with_images(
                prompt=HOLIDAY_EXTRACTION_VISION_PROMPT,
                image_data_urls=image_data_urls,
                system_prompt="You extract holiday tables accurately and return strict JSON.",
                model=self.openai_model,
            )
        except Exception as exc:
            logger.warning("OpenAI vision holiday fallback failed: %s", exc)
            return []

        return self._parse_holidays_payload(payload)

    def _render_pdf_images_for_openai(self, pdf_path: Path) -> List[str]:
        try:
            import fitz
        except ImportError as exc:
            raise ValueError("PyMuPDF is not installed. Install pymupdf first.") from exc

        image_data_urls: List[str] = []
        with fitz.open(str(pdf_path)) as document:
            pages_to_read = min(self.openai_max_pages, document.page_count)
            zoom = self.openai_image_dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            for page_index in range(pages_to_read):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                png_bytes = pixmap.tobytes("png")
                data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode(
                    "ascii"
                )
                image_data_urls.append(data_url)

        return image_data_urls

    def _parse_holidays_payload(self, payload: Dict[str, object]) -> List[Dict[str, str]]:
        holidays = payload.get("holidays")
        if not isinstance(holidays, list):
            return []

        parsed: List[Dict[str, str]] = []
        for item in holidays:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("date")
            raw_name = item.get("name")
            raw_category = item.get("category")
            if not isinstance(raw_date, str):
                continue
            try:
                date.fromisoformat(raw_date)
            except ValueError:
                continue
            name = str(raw_name).strip() if raw_name is not None else "Unnamed Holiday"
            parsed.append(
                {
                    "date": raw_date,
                    "name": name or "Unnamed Holiday",
                    "category": _normalize_category(
                        str(raw_category or ""),
                        name_hint=name,
                    ),
                }
            )
        return _dedupe_holidays(parsed)

    def _is_confident(self, entries: List[Dict[str, str]]) -> bool:
        if not entries:
            return False
        return score_holiday_entries(entries) >= self.confidence_threshold

    def _is_confident_enough(self, entries: List[Dict[str, str]]) -> bool:
        if len(entries) < self.min_confident_entries:
            return False
        return self._is_confident(entries)

    def _entry_score(self, entries: List[Dict[str, str]]) -> float:
        return score_holiday_entries(entries)

    def _send_failure_alert(self, file_path: Path, detail: str) -> None:
        if not self.alert_recipient:
            return

        subject = f"[HR Automation] Holiday sync extraction failed: {file_path.name}"
        body = (
            "Holiday extraction failed after all local fallbacks.\n\n"
            f"File: {file_path}\n"
            f"Detail: {detail}\n"
            f"Time (UTC): {datetime.now(timezone.utc).isoformat()}\n"
        )
        try:
            self.email_service.send_email(self.alert_recipient, subject, body)
        except Exception as exc:
            logger.warning("Failed to send holiday extraction alert email: %s", exc)

    @staticmethod
    def _dedupe_category_entries(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
        by_date: Dict[str, str] = {}
        for item in entries:
            iso_date = item["date"]
            name = item["name"]
            existing_name = by_date.get(iso_date)
            if existing_name is None:
                by_date[iso_date] = name
                continue
            if existing_name in {"Unnamed Holiday", "Hari Libur Nasional"} and name:
                by_date[iso_date] = name
        return [{"date": iso_date, "name": by_date[iso_date]} for iso_date in sorted(by_date)]

    def _read_file(self) -> Dict[str, Dict[str, List[Dict[str, str]]]]:
        if not self.holidays_file.exists():
            return {}
        try:
            data = json.loads(self.holidays_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}

        validated: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
        for year, year_values in data.items():
            if not isinstance(year, str):
                continue

            categories = {
                HOLIDAY_CATEGORY_LIBUR_NASIONAL: [],
                HOLIDAY_CATEGORY_CUTI_BERSAMA: [],
            }

            if isinstance(year_values, dict):
                for category_key, raw_entries in year_values.items():
                    if not isinstance(raw_entries, list):
                        continue
                    category = _normalize_category(str(category_key), "")
                    for item in raw_entries:
                        if not isinstance(item, dict):
                            continue
                        raw_date = item.get("date")
                        raw_name = item.get("name")
                        if not isinstance(raw_date, str) or not isinstance(raw_name, str):
                            continue
                        categories[category].append({"date": raw_date, "name": raw_name})
            else:
                continue

            validated[year] = {
                category: self._dedupe_category_entries(entries)
                for category, entries in categories.items()
            }
        return validated

    def _write_file(self, data: Dict[str, Dict[str, List[Dict[str, str]]]]) -> None:
        self.holidays_file.parent.mkdir(parents=True, exist_ok=True)
        self.holidays_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

holiday_sync_service = HolidaySyncService()
