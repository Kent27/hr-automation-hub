from __future__ import annotations

from datetime import date
from typing import Iterable, List

from app.automations.base import Automation, AutomationResult


class AutomationRunner:
    def __init__(self, automations: Iterable[Automation]):
        self._order: List[str] = []
        self._automations: dict[str, Automation] = {}
        for automation in automations:
            self._order.append(automation.name)
            self._automations[automation.name] = automation

    def list_automations(self) -> List[str]:
        return list(self._order)

    def run_due(self, run_date: date) -> List[AutomationResult]:
        results: List[AutomationResult] = []
        for automation_name in self._order:
            automation = self._automations[automation_name]
            if automation.should_run(run_date):
                results.append(automation.run(run_date))
        return results

    def run_one(self, name: str, run_date: date, force: bool = False) -> AutomationResult:
        automation = self._automations.get(name)
        if not automation:
            raise ValueError(f"Unknown automation: {name}")
        if not force and not automation.should_run(run_date):
            return AutomationResult(
                automation=name,
                ran=False,
                skipped_count=1,
                message="Automation is not due on this date. Use --force to run anyway.",
            )
        return automation.run(run_date)
