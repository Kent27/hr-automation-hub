# Services AGENTS.md

This directory contains file-backed business services shared by both FastAPI routers and Typer CLI commands.

## Conventions

- Keep service modules framework-agnostic; avoid importing FastAPI/Typer into service code.
- Expose a module singleton at the bottom of each service file (for app runtime wiring).
- Preserve constructor injection hooks (`*_instance`, custom paths) when extending services.
- Read/write paths must come from `app.config` defaults or explicit injected paths, not hardcoded strings.
- Use `read_json_list`/`write_json_list` only for list-shaped JSON files.
- If a service needs dict-shaped JSON (for example holidays by year), implement dedicated read/write handling.
- Validate month/date inputs using existing strict ISO patterns (`YYYY-MM`, `YYYY-MM-DD`).
- Keep side effects explicit:
  - OpenAI HTTP calls for invoice + holiday extraction (`OPENAI_MODEL`)
  - Local Ollama HTTP calls (`OLLAMA_BASE_URL`) for non-extraction/test flows
  - Gmail send operations
  - PDF generation/writes to `output/`

## Gotchas

- `ClaimService.add_claim()` parses invoice unless `amount_override` is provided.
- `InvoiceParser` and `HolidaySyncService` send alert email on final extraction failure unless `EXTRACTION_ALERT_EMAIL` is empty.
- `OllamaService` expects JSON response shape from `/api/chat`; malformed output raises `ValueError`.
- `OpenAIJsonService` expects `chat.completions` JSON response; malformed content raises `ValueError`.
- `EmailService._get_credentials(interactive=False)` raises if OAuth files are missing/invalid.
- `InvoiceParser` flow is now `OpenAI text on embedded PDF text -> OpenAI vision`.
- `HolidaySyncService` flow is now `OpenAI vision -> OpenAI text fallback on embedded PDF text`.
- `load_holiday_entries()` expects `{"year": {"libur_nasional": [...], "cuti_bersama": [...]}}` records.
- Tests should inject fake dependencies and temp paths; default singletons can mutate real `data/` files.

## Key Files

| File | Why it matters |
|------|----------------|
| `storage_utils.py` | Canonical JSON list persistence behavior used by most services. |
| `claim_service.py` | Benefit capping + invoice parsing flow; common source of extraction side effects. |
| `email_service.py` | Gmail OAuth + send abstractions used by payslip and reminder flows. |
| `invoice_parser.py` | OpenAI-backed invoice extraction with text/vision fallback and failure alerting. |
| `holiday_pdf_discovery_service.py` | Trusted `.go.id` holiday PDF discovery, scoring, and download. |
| `openai_json_service.py` | JSON-only OpenAI wrapper for text + image chat payloads. |
| `holiday_sync_service.py` | OpenAI vision-first holiday extraction + OpenAI text fallback + year-keyed persistence. |
| `ollama_service.py` | JSON-only local model call wrapper used by extraction fallbacks. |
