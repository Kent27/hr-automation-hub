# Automations AGENTS.md

This directory defines scheduled/manual automation units and the runner/registration contract for them.

## Conventions

- Implement new automations against `Automation` (`name`, `should_run(run_date)`, `run(run_date)`).
- Always return `AutomationResult`; do not return raw dicts from automation classes.
- Register automations in `registry.py`; registration order is execution order for `run_due()`.
- Manual-only automations should keep `should_run()` false and expose explicit manual entrypoints when needed.
- Keep runner semantics intact:
  - `run_due()` executes only automations where `should_run()` is true.
  - `run_one(..., force=False)` skips not-due automations instead of hard failing.

## Gotchas

- `holiday-reminder` runs on the last day of month but emails next month’s holidays.
- `holiday-reminder` has no persisted run-log dedupe; repeated manual runs resend reminders.
- `holiday-sync` requires a PDF path and is invoked through `run_with_pdf(...)` from CLI.
- `holiday sync-auto` CLI performs trusted `.go.id` PDF discovery first, then calls `holiday-sync`.
- Automations are imported at CLI startup; avoid import-time side effects in new modules.

## Key Files

| File | Why it matters |
|------|----------------|
| `base.py` | Source of truth for automation interface + result schema. |
| `runner.py` | Due/force execution behavior used by CLI automation commands. |
| `registry.py` | Central registration and execution order definition. |
| `holiday_reminder.py` | Month-end reminder automation with dependency injection and per-employee email sends. |
