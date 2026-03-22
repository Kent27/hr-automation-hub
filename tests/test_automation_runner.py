from datetime import date

from app.automations.base import Automation, AutomationResult
from app.automations.runner import AutomationRunner


class StubAutomation(Automation):
    def __init__(self, name: str, due: bool):
        self.name = name
        self._due = due

    def should_run(self, run_date: date) -> bool:
        return self._due

    def run(self, run_date: date) -> AutomationResult:
        return AutomationResult(automation=self.name, ran=True, processed_count=1)


def test_run_due_only_runs_due_automations():
    due_automation = StubAutomation(name="due-automation", due=True)
    not_due_automation = StubAutomation(name="not-due-automation", due=False)

    runner = AutomationRunner([due_automation, not_due_automation])
    results = runner.run_due(date(2026, 2, 28))

    assert [result.automation for result in results] == ["due-automation"]


def test_run_one_respects_due_window_without_force():
    automation = StubAutomation(name="manual-automation", due=False)
    runner = AutomationRunner([automation])

    result = runner.run_one("manual-automation", run_date=date(2026, 2, 10), force=False)

    assert result.ran is False
    assert result.skipped_count == 1


def test_run_one_runs_when_forced():
    automation = StubAutomation(name="manual-automation", due=False)
    runner = AutomationRunner([automation])

    result = runner.run_one("manual-automation", run_date=date(2026, 2, 10), force=True)

    assert result.ran is True
    assert result.processed_count == 1
