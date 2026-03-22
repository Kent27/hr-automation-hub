# Extraction Architecture (Current)

This file captures the current extraction behavior after multiple iterations.

## Invoice Extraction (Local-first)

`app/services/invoice_parser.py` uses:

1. Rule parsing on embedded text
2. OCR via PaddleOCR (`app/services/ocr_service.py`) when needed
3. Ollama text JSON fallback (`qwen3.5:0.8b` by default)
4. Failure alert email (`EXTRACTION_ALERT_EMAIL`) on final failure

## Holiday Extraction (OpenAI vision first)

`app/services/holiday_sync_service.py` uses:

1. OpenAI vision extraction (`OPENAI_MODEL`, recommended `gpt-4o`) from rendered PDF page images
2. Ollama text JSON fallback from embedded PDF text when vision result is not confident enough
3. Failure alert email (`EXTRACTION_ALERT_EMAIL`) on final failure

Holiday sync runtime no longer uses OCR.

## PDF Discovery (for `holiday sync-auto`)

`app/services/holiday_pdf_discovery_service.py`:

1. Reads seed URLs (`HOLIDAY_DISCOVERY_SEED_URLS`)
2. Parses page links and filters to trusted domains (`HOLIDAY_DISCOVERY_ALLOWED_DOMAIN_SUFFIXES`)
3. Scores PDF candidates by year + keywords
4. Downloads first valid PDF and hands it to holiday sync

## Main environment knobs

- `OLLAMA_BASE_URL`, `OLLAMA_TEXT_MODEL`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `OPENAI_HOLIDAY_FALLBACK_ENABLED`, `OPENAI_HOLIDAY_MAX_PAGES`, `OPENAI_HOLIDAY_IMAGE_DPI`
- `OCR_DPI`, `MAX_OCR_PAGES_INVOICE`, `OCR_LANG` (invoice path only)
- `EXTRACTION_ALERT_EMAIL`

## Validation baseline

Use Docker tests as source of truth:

```bash
docker compose run --rm hr-automation-hub python -m pytest /app/tests -q
```
