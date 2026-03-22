from __future__ import annotations

from typing import Dict, List, Optional


def score_invoice_extraction(
    total_amount: float,
    invoice_id: Optional[str],
    currency: Optional[str],
) -> float:
    score = 0.0
    if total_amount > 0:
        score += 0.7
    if currency:
        score += 0.2
    if invoice_id:
        score += 0.1
    return min(score, 1.0)


def score_holiday_entries(entries: List[Dict[str, str]]) -> float:
    if not entries:
        return 0.0

    names_present = sum(1 for entry in entries if str(entry.get("name") or "").strip())
    unique_dates = len({entry.get("date") for entry in entries if entry.get("date")})

    named_ratio = names_present / len(entries)
    uniqueness_ratio = unique_dates / len(entries)

    score = 0.0
    score += 0.4
    score += 0.3 * named_ratio
    score += 0.2 * uniqueness_ratio

    months = {
        value[5:7]
        for value in (entry.get("date") for entry in entries)
        if isinstance(value, str) and len(value) >= 7
    }
    if len(entries) >= 5 or len(months) >= 2:
        score += 0.1

    return min(score, 1.0)
