"""Gmail API adapter producing the provider-neutral InboundEmail model."""

import base64
import os
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import get_required_setting
from app.models.inbound_email import InboundAttachment, InboundEmail


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
PROCESSED_LABEL = "RFQ_INTAKE_PROCESSED"


class GmailInbox:
    def __init__(self):
        credentials = Credentials(
            token=None,
            refresh_token=get_required_setting("GMAIL_REFRESH_TOKEN"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=get_required_setting("GMAIL_CLIENT_ID"),
            client_secret=get_required_setting("GMAIL_CLIENT_SECRET"),
            scopes=GMAIL_SCOPES,
        )
        self.mailbox = os.getenv(
            "GMAIL_INBOX_ADDRESS",
            "rfq.intake.processing@gmail.com",
        ).lower()
        self.service = build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def ensure_processed_label(self) -> str:
        labels = self.service.users().labels().list(userId="me").execute().get("labels", [])
        found = next((item for item in labels if item["name"] == PROCESSED_LABEL), None)
        if found:
            return found["id"]
        return self.service.users().labels().create(
            userId="me",
            body={"name": PROCESSED_LABEL, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        ).execute()["id"]

    def list_unprocessed(self, max_results: int = 25) -> list[InboundEmail]:
        label_id = self.ensure_processed_label()
        response = self.service.users().messages().list(
            userId="me",
            q=f"in:inbox -label:{PROCESSED_LABEL}",
            maxResults=max_results,
        ).execute()
        emails = []
        for item in response.get("messages", []):
            raw_message = self.service.users().messages().get(
                userId="me", id=item["id"], format="raw"
            ).execute()
            emails.append(self._parse_message(raw_message))
        self._label_id = label_id
        return emails

    def mark_processed(self, email: InboundEmail) -> None:
        self.service.users().messages().modify(
            userId="me",
            id=email.message_id,
            body={"addLabelIds": [self._label_id]},
        ).execute()

    def _parse_message(self, message: dict[str, Any]) -> InboundEmail:
        raw_bytes = _decode_base64url(message["raw"])
        mime = message_from_bytes(raw_bytes)
        attachments = []
        plain_parts = []
        html_parts = []
        for part in mime.walk():
            if part.is_multipart():
                continue
            content = part.get_payload(decode=True) or b""
            filename = _decode_header_value(part.get_filename())
            if filename:
                attachments.append(InboundAttachment(
                    filename=filename,
                    mime_type=part.get_content_type(),
                    content=content,
                ))
                continue
            if part.get_content_maintype() != "text":
                continue
            charset = part.get_content_charset() or "utf-8"
            text_content = content.decode(charset, errors="replace")
            if part.get_content_subtype() == "plain":
                plain_parts.append(text_content)
            elif part.get_content_subtype() == "html":
                html_parts.append(_HTMLText().convert(text_content))

        body = "\n\n".join(plain_parts or html_parts).strip()
        sender = parseaddr(str(make_header(decode_header(mime.get("From", "")))))[1]
        date_header = mime.get("Date")
        received_at = None
        if date_header:
            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(date_header)
                if received_at.tzinfo is None:
                    received_at = received_at.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                received_at = None

        return InboundEmail(
            provider="gmail",
            mailbox=self.mailbox,
            message_id=message["id"],
            sender=sender,
            subject=_decode_header_value(mime.get("Subject")),
            received_at=received_at or datetime.now(timezone.utc),
            body=body,
            attachments=attachments,
        )


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)

    def convert(self, value):
        self.feed(value)
        return "\n".join(self.parts)


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _decode_header_value(value: str | None) -> str | None:
    if value is None:
        return None
    return str(make_header(decode_header(value)))
