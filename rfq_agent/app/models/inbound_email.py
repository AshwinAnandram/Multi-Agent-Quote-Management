"""Provider-neutral email and attachment representation for RFQ intake."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InboundAttachment(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    filename: str
    mime_type: str | None = None
    content: bytes


class InboundEmail(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: str
    mailbox: str
    message_id: str
    sender: str
    subject: str | None = None
    received_at: datetime | None = None
    body: str = ""
    attachments: list[InboundAttachment] = Field(default_factory=list)

    @property
    def source_message_id(self) -> str:
        return f"{self.provider}:{self.mailbox.lower()}:{self.message_id}"
