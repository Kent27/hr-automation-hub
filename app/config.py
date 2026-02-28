from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

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

COMPANY_NAME = os.getenv("COMPANY_NAME", "PT. Solutionesia Teknologi Digital")

GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL")
SENDER_NAME = os.getenv("SENDER_NAME", "Kent")
GMAIL_CREDENTIALS_PATH = Path(
    os.getenv("GMAIL_CREDENTIALS_PATH", PROJECT_ROOT / "credentials" / "client_secret.json")
)
GMAIL_TOKEN_PATH = Path(
    os.getenv("GMAIL_TOKEN_PATH", PROJECT_ROOT / "credentials" / "token.json")
)
