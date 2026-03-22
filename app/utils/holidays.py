from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Set

from app.config import HOLIDAYS_FILE


HOLIDAY_CATEGORY_LIBUR_NASIONAL = "libur_nasional"
HOLIDAY_CATEGORY_CUTI_BERSAMA = "cuti_bersama"
HOLIDAY_CATEGORIES = (
    HOLIDAY_CATEGORY_LIBUR_NASIONAL,
    HOLIDAY_CATEGORY_CUTI_BERSAMA,
)


@dataclass(frozen=True)
class HolidayEntry:
    holiday_date: date
    name: str
    category: str = HOLIDAY_CATEGORY_LIBUR_NASIONAL


def _normalize_category(raw_category: str | None, name_hint: str = "") -> str:
    for value in [raw_category or "", name_hint]:
        lowered = value.strip().lower()
        if not lowered:
            continue
        if "cuti" in lowered:
            return HOLIDAY_CATEGORY_CUTI_BERSAMA
        if "libur nasional" in lowered or "hari libur" in lowered or "nasional" in lowered:
            return HOLIDAY_CATEGORY_LIBUR_NASIONAL
    return HOLIDAY_CATEGORY_LIBUR_NASIONAL


def load_holiday_entries(holidays_file: Path | None = None) -> List[HolidayEntry]:
    file_path = holidays_file or HOLIDAYS_FILE
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    entries: List[HolidayEntry] = []

    def append_entry(raw_date: str, raw_name: str, raw_category: str | None) -> None:
        try:
            parsed_date = date.fromisoformat(raw_date)
        except ValueError:
            return
        category = _normalize_category(raw_category, raw_name)
        entries.append(
            HolidayEntry(
                holiday_date=parsed_date,
                name=raw_name.strip(),
                category=category,
            )
        )

    for year_values in data.values():
        if not isinstance(year_values, dict):
            continue

        for category_key, category_items in year_values.items():
            if not isinstance(category_items, list):
                continue
            for item in category_items:
                if not isinstance(item, dict):
                    continue
                raw_date = item.get("date")
                raw_name = item.get("name")
                if not isinstance(raw_date, str) or not isinstance(raw_name, str):
                    continue
                append_entry(raw_date, raw_name, str(category_key))

    return sorted(entries, key=lambda entry: (entry.holiday_date, entry.category, entry.name))


def _entry_dates(entries: List[HolidayEntry]) -> Set[date]:
    return {entry.holiday_date for entry in entries}


def _entries_for_year(entries: List[HolidayEntry], year: int) -> List[HolidayEntry]:
    return [entry for entry in entries if entry.holiday_date.year == year]


def load_holidays(holidays_file: Path | None = None) -> Set[date]:
    return _entry_dates(load_holiday_entries(holidays_file))


def get_holidays_for_year(year: int, holidays_file: Path | None = None) -> Set[date]:
    entries = load_holiday_entries(holidays_file)
    return _entry_dates(_entries_for_year(entries, year))


def get_holiday_entries_for_year(
    year: int, holidays_file: Path | None = None
) -> List[HolidayEntry]:
    entries = load_holiday_entries(holidays_file)
    return _entries_for_year(entries, year)
