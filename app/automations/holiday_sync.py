from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.automations.base import Automation, AutomationResult
from app.services.holiday_sync_service import HolidaySyncService, holiday_sync_service

logger = logging.getLogger(__name__)


class HolidaySyncAutomation(Automation):
    """Parse an official government PDF to populate holidays_id.json.

    This automation is manual-only (should_run always returns False).
    Trigger it via CLI:
        python3 -m app.cli holiday sync <pdf-path>
    """

    name = "holiday-sync"

    def __init__(
        self,
        sync_service: HolidaySyncService = holiday_sync_service,
    ):
        self.sync_service = sync_service

    def should_run(self, run_date: date) -> bool:
        return False

    def run(self, run_date: date) -> AutomationResult:
        return AutomationResult(
            automation=self.name,
            ran=False,
            message="holiday-sync requires a PDF file. Use: python3 -m app.cli holiday sync <pdf-path>",
        )

    def run_with_pdf(self, pdf_path: Path, _run_date: date) -> AutomationResult:

        try:
            synced_dates = self.sync_service.sync_from_pdf(pdf_path)
        except Exception as exc:
            logger.error("Holiday sync failed for %s: %s", pdf_path, exc)
            return AutomationResult(
                automation=self.name,
                ran=True,
                failed_count=1,
                message=f"Failed to sync holidays from {pdf_path.name}: {exc}",
            )

        years = sorted({d.year for d in synced_dates})

        return AutomationResult(
            automation=self.name,
            ran=True,
            processed_count=len(synced_dates),
            message=f"Synced {len(synced_dates)} holidays for year(s) {years} from {pdf_path.name}",
        )


holiday_sync_automation = HolidaySyncAutomation()
