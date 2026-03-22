# Tests AGENTS.md

This directory contains pytest coverage for service and automation behavior using local, isolated filesystem fixtures.

## Conventions

- Prefer unit-style tests with `tmp_path` and injected service instances.
- Never rely on module singletons in tests when files/network are involved.
- For claim tests, pass `amount_override` (or inject fake OpenAI services) to avoid live extraction dependencies.
- For holiday/email automations, inject fake services instead of real API clients.
- For holiday sync tests, prefer fake OpenAI services and override PDF/image render helpers to keep tests offline and deterministic.
- Keep assertions focused on behavior contracts (counts, idempotency, persisted state shape).
- Prefer asserting `AutomationResult` fields explicitly (`ran`, `processed_count`, `skipped_count`, `failed_count`).
- Use explicit dates in tests to make schedule logic deterministic.
- Prefer running tests through Docker runtime:
  - `docker compose run --rm hr-automation-hub python -m pytest /app/tests -q`

## Gotchas

- Host Python may not match runtime deps; Docker test path is the source of truth.
- Using default service singletons can mutate real `data/` files outside `tmp_path`.
- Networked integrations (OpenAI/Ollama/Gmail) should be avoided in test paths unless explicitly integration-testing.

## Key Files

| File | Why it matters |
|------|----------------|
| `test_claim_service.py` | Canonical pattern for file-isolated service tests with `tmp_path`. |
| `test_holiday_reminder_automation.py` | Fake email injection pattern for holiday reminder behavior checks. |
| `test_holiday_sync_automation.py` | Fake sync service pattern for PDF/holiday write behavior without API calls. |
| `test_holiday_sync_service.py` | Holiday extractor tests for OpenAI vision-first flow, OpenAI text fallback, and failure alert path. |
| `test_invoice_parser.py` | Invoice extractor tests for OpenAI text/vision flow and failure alert path. |
