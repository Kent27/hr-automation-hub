from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import (
    GMAIL_CREDENTIALS_PATH,
    GMAIL_SENDER_EMAIL,
    GMAIL_TOKEN_PATH,
    SENDER_NAME,
)
from app.models.payslip_models import PayslipData


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class EmailService:
    def __init__(
        self,
        sender_email: Optional[str] = None,
        credentials_path: Path = GMAIL_CREDENTIALS_PATH,
        token_path: Path = GMAIL_TOKEN_PATH,
    ):
        self.sender_email = sender_email or GMAIL_SENDER_EMAIL
        self.credentials_path = credentials_path
        self.token_path = token_path

    def setup_oauth(self) -> None:
        self._get_credentials(interactive=True)

    def send_payslip(self, payslip: PayslipData, pdf_path: str) -> None:
        if not self.sender_email:
            raise ValueError("GMAIL_SENDER_EMAIL is not set")

        service = self._build_service()
        message = EmailMessage()
        message["To"] = payslip.employee_email
        message["From"] = f"{SENDER_NAME} <{self.sender_email}>"
        message["Subject"] = f"Payslip for {payslip.pay_period_label}"

        first_name = payslip.employee_name.split(" ")[0]
        body = (
            f"Dear {first_name},\n\n"
            f"Attached is your payslip for {payslip.pay_period_label}.\n\n"
            "Thanks.\n\n"
            f"Best Regards,\n{SENDER_NAME}"
        )
        message.set_content(body)

        pdf_bytes = Path(pdf_path).read_bytes()
        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=Path(pdf_path).name,
        )

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        service.users().messages().send(userId="me", body={"raw": encoded_message}).execute()

    def _build_service(self):
        credentials = self._get_credentials(interactive=False)
        return build("gmail", "v1", credentials=credentials)

    def _get_credentials(self, interactive: bool) -> Credentials:
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            if not interactive:
                raise ValueError("Gmail credentials not available. Run auth setup first.")
            if not self.credentials_path.exists():
                raise ValueError("Gmail client secrets not found.")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        return creds


email_service = EmailService()
