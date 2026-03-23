from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_bool(value: str, default: bool = False) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
CLAIMS_DIR = DATA_DIR / "claims"
EMPLOYEES_FILE = DATA_DIR / "employees.json"
CLAIMS_FILE = DATA_DIR / "claims.json"
HOLIDAYS_FILE = DATA_DIR / "holidays_id.json"

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", PROJECT_ROOT / "output"))
PAYSLIP_OUTPUT_DIR = OUTPUT_DIR / "payslips"

PAYSLIP_TEMPLATE = Path(
    os.getenv("PAYSLIP_TEMPLATE", PROJECT_ROOT / "templates" / "payslip.html")
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_INVOICE_MAX_PAGES = int(os.getenv("OPENAI_INVOICE_MAX_PAGES", "3"))
OPENAI_INVOICE_IMAGE_DPI = int(os.getenv("OPENAI_INVOICE_IMAGE_DPI", "170"))
OPENAI_HOLIDAY_FALLBACK_ENABLED = _parse_bool(
    os.getenv("OPENAI_HOLIDAY_FALLBACK_ENABLED", "true"),
    default=True,
)
OPENAI_HOLIDAY_MAX_PAGES = int(os.getenv("OPENAI_HOLIDAY_MAX_PAGES", "6"))
OPENAI_HOLIDAY_IMAGE_DPI = int(os.getenv("OPENAI_HOLIDAY_IMAGE_DPI", "170"))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "qwen3.5:0.8b")
HYBRID_CONFIDENCE_THRESHOLD = float(os.getenv("HYBRID_CONFIDENCE_THRESHOLD", "0.85"))
EXTRACTION_ALERT_EMAIL = os.getenv("EXTRACTION_ALERT_EMAIL", "kentkent2797@gmail.com")
FX_USD_IDR_API_URL = os.getenv("FX_USD_IDR_API_URL", "https://open.er-api.com/v6/latest/USD")
FX_REQUEST_TIMEOUT_SECONDS = int(os.getenv("FX_REQUEST_TIMEOUT_SECONDS", "20"))
FX_RATE_CACHE_SECONDS = int(os.getenv("FX_RATE_CACHE_SECONDS", "3600"))
HOLIDAY_DISCOVERY_SEED_URLS = _split_csv(
    os.getenv(
        "HOLIDAY_DISCOVERY_SEED_URLS",
        "https://www.kemenkopmk.go.id/,https://www.bi.go.id/id/publikasi/Kalender/Documents/Kalender-Libur-BI-2026.pdf",
    )
)
HOLIDAY_DISCOVERY_ALLOWED_DOMAIN_SUFFIXES = _split_csv(
    os.getenv("HOLIDAY_DISCOVERY_ALLOWED_DOMAIN_SUFFIXES", ".go.id")
)
HOLIDAY_DISCOVERY_TIMEOUT_SECONDS = int(
    os.getenv("HOLIDAY_DISCOVERY_TIMEOUT_SECONDS", "20")
)
HOLIDAY_DISCOVERY_MAX_PDF_BYTES = int(
    os.getenv("HOLIDAY_DISCOVERY_MAX_PDF_BYTES", str(15 * 1024 * 1024))
)
HOLIDAY_DISCOVERY_MAX_CANDIDATES = int(
    os.getenv("HOLIDAY_DISCOVERY_MAX_CANDIDATES", "20")
)
HOLIDAY_DISCOVERY_OUTPUT_DIR = Path(
    os.getenv("HOLIDAY_DISCOVERY_OUTPUT_DIR", OUTPUT_DIR / "holiday-pdfs")
)
HOLIDAY_MIN_CONFIDENT_ENTRIES = int(os.getenv("HOLIDAY_MIN_CONFIDENT_ENTRIES", "2"))

COMPANY_NAME = os.getenv("COMPANY_NAME", "PT. Solutionesia Teknologi Digital")

GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL")
SENDER_NAME = os.getenv("SENDER_NAME", "Kent")
GMAIL_CREDENTIALS_PATH = Path(
    os.getenv("GMAIL_CREDENTIALS_PATH", PROJECT_ROOT / "credentials" / "client_secret.json")
)
GMAIL_TOKEN_PATH = Path(
    os.getenv("GMAIL_TOKEN_PATH", PROJECT_ROOT / "credentials" / "token.json")
)
