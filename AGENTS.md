# AGENTS.md

## Project Snapshot

- **Type**: Single Python project with both FastAPI API and Typer CLI surfaces.
- **Stack**: Python, FastAPI, Typer, Pydantic v2, Gmail API, Jinja2, WeasyPrint, PaddleOCR, PyMuPDF, Ollama HTTP API, OpenAI API.
- **Styling**: Server-rendered HTML payslip template (`templates/payslip.html`) converted to PDF.
- **State**: File-backed JSON state in `data/` (no database layer).
- **Runtime**: Docker + Conda (`Dockerfile`, `docker-compose.yml`, `environment.yml`).

## Non-Obvious Conventions

### Architecture
- Keep domain logic in `app/services/*`; API routers and CLI commands are thin orchestration layers.
- Keep service modules framework-agnostic so API and CLI reuse the same behavior.
- Preserve dependency-injection constructor params (`*_instance`) in services/automations; tests rely on this seam.
- Keep module-level singleton exports (`*_service`, `*_automation`) for runtime wiring consistency.
- Invoice extraction stages: `rules -> OCR -> Ollama text JSON -> alert email on final failure`.
- Holiday extraction stages: `OpenAI vision (gpt-4o) -> Ollama text on embedded PDF text -> alert email on final failure`.
- Date formats are strict and shared across surfaces:
  - payroll month: `YYYY-MM`
  - run date / holiday date: `YYYY-MM-DD`
- Keep path defaults centralized in `app/config.py`; avoid hardcoded filesystem paths.

### Security
- Secrets are environment-driven (`.env` / Compose env); never hardcode or log them.
- Gmail OAuth artifacts in `credentials/` are local-only and sensitive.
- `EXTRACTION_ALERT_EMAIL` receives parser failures; keep it empty in local test runs if you do not want alerts.
- `OPENAI_API_KEY` + `OPENAI_MODEL` are required for holiday vision fallback quality.
- When running in Docker, Ollama is usually on host; set `OLLAMA_BASE_URL=http://host.docker.internal:11434`.
- Treat employee/claim runtime data as private operational data, not sample fixtures.
- Keep generated payslip PDFs in `output/` as local artifacts unless explicitly asked to version them.

### Gotchas
- `holiday-sync` is intentionally manual-only (`should_run()` returns `False`); execute via `holiday sync <pdf-path>`.
- `holiday sync-auto --year YYYY` discovers trusted `.go.id` PDFs first, then runs `holiday-sync`.
- `holiday-reminder` executes at month-end but targets next month’s holiday dates.
- `holiday-reminder` no longer persists run-log idempotency; repeated runs on same day resend reminders.
- `claim add` without `--amount` requires OCR + Ollama runtime dependencies to be available.
- `payslip send --pdf` reuses an existing PDF and intentionally skips regeneration.
- Prefer Docker commands for execution/testing: `docker compose run --rm hr-automation-hub ...`.

## JIT Index

- `app/services/` → [see AGENTS.md](app/services/AGENTS.md)
- `app/automations/` → [see AGENTS.md](app/automations/AGENTS.md)
- `tests/` → [see AGENTS.md](tests/AGENTS.md)
- `app/config.py` → canonical env var names and file path defaults
- `app/cli.py` → command entrypoints, option parsing, and date format enforcement
- `app/services/storage_utils.py` → list-shaped JSON persistence contract
- `app/utils/holidays.py` → holiday entry loading for `{"year": {"libur_nasional": [...], "cuti_bersama": [...]}}` schema
- `app/services/claim_service.py` → benefit capping + invoice parse/override behavior
- `app/services/email_service.py` → Gmail OAuth credential flow and send helpers
- `app/services/ocr_service.py` → PaddleOCR + PyMuPDF extraction layer
- `app/services/ollama_service.py` → local Ollama JSON chat wrapper
- `app/services/openai_json_service.py` → OpenAI JSON + image-enabled chat wrapper
- `app/services/holiday_pdf_discovery_service.py` → trusted `.go.id` PDF discovery and download scoring
- `app/services/holiday_sync_service.py` → OpenAI vision-first holiday extraction + year-keyed holiday writes
- `app/automations/runner.py` → due/force execution semantics
- `app/automations/holiday_reminder.py` → month-end scheduling + reminder email composition
