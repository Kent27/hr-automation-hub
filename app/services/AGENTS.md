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
  - Local OCR calls for invoice extraction (PaddleOCR / PyMuPDF)
  - Local Ollama HTTP calls (`OLLAMA_BASE_URL`)
  - OpenAI HTTP calls for holiday vision fallback (`OPENAI_MODEL`)
  - Gmail send operations
  - PDF generation/writes to `output/`

## Gotchas

- `ClaimService.add_claim()` parses invoice unless `amount_override` is provided.
- `InvoiceParser` and `HolidaySyncService` send alert email on final extraction failure unless `EXTRACTION_ALERT_EMAIL` is empty.
- `OCRService` lazy-imports `paddleocr` and `fitz`; missing deps raise `ValueError` at runtime.
- `OllamaService` expects JSON response shape from `/api/chat`; malformed output raises `ValueError`.
- `OpenAIJsonService` expects `chat.completions` JSON response; malformed content raises `ValueError`.
- `EmailService._get_credentials(interactive=False)` raises if OAuth files are missing/invalid.
- `HolidaySyncService` flow is now `OpenAI vision -> Ollama text fallback on embedded PDF text` (no OCR stage for holiday sync runtime).
- `load_holiday_entries()` expects `{"year": {"libur_nasional": [...], "cuti_bersama": [...]}}` records.
- Tests should inject fake dependencies and temp paths; default singletons can mutate real `data/` files.

## Key Files

| File | Why it matters |
|------|----------------|
| `storage_utils.py` | Canonical JSON list persistence behavior used by most services. |
| `claim_service.py` | Benefit capping + invoice parsing flow; common source of extraction side effects. |
| `email_service.py` | Gmail OAuth + send abstractions used by payslip and reminder flows. |
| `invoice_parser.py` | Hybrid invoice extraction (`rules -> OCR -> Ollama`) with failure alerting. |
| `holiday_pdf_discovery_service.py` | Trusted `.go.id` holiday PDF discovery, scoring, and download. |
| `openai_json_service.py` | JSON-only OpenAI wrapper for text + image chat payloads. |
| `holiday_sync_service.py` | OpenAI vision-first holiday extraction + Ollama text fallback + year-keyed persistence. |
| `ocr_service.py` | OCR text extraction for images and rendered PDF pages. |
| `ollama_service.py` | JSON-only local model call wrapper used by extraction fallbacks. |
