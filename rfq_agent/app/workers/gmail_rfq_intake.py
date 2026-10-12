"""Poll one Gmail inbox and route all messages through shared RFQ intake."""

import logging
import os
import time

from app.agents.extraction import RFQExtractionAgent
from app.azure_client import create_azure_openai_client
from app.config import get_required_setting
from app.repositories.bid_repository import apply_closed_bid_outcome
from app.repositories.rfq_repository import save_inbound_rfq
from app.services.gmail_client import GmailInbox
from app.services.rfq_intake import extract_inbound_email, resolve_bid_outcome


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("rfq-gmail-intake")


def poll_once(inbox: GmailInbox, extraction_agent: RFQExtractionAgent) -> int:
    processed = 0
    for email in inbox.list_unprocessed():
        try:
            intake = extract_inbound_email(email, extraction_agent)
            outcome = resolve_bid_outcome(intake)
            if outcome:
                saved = apply_closed_bid_outcome(
                    **outcome,
                    source_message_id=email.source_message_id,
                )
                if not saved["matched"]:
                    saved = save_inbound_rfq(email, intake)
            else:
                saved = save_inbound_rfq(email, intake)
            inbox.mark_processed(email)
            logger.info(
                "Handled Gmail message id=%s bid_id=%s rfq_id=%s status=%s duplicate=%s",
                email.message_id,
                saved.get("bid_id"),
                saved.get("rfq_id"),
                saved.get("status", saved.get("processing_status")),
                saved["duplicate"],
            )
            processed += 1
        except Exception:
            logger.exception("Gmail message intake failed; message remains unlabelled for retry.")
    return processed


def main() -> None:
    interval = max(15, int(os.getenv("GMAIL_POLL_INTERVAL_SECONDS", "60")))
    extraction_agent = RFQExtractionAgent(
        client=create_azure_openai_client(),
        deployment_name=get_required_setting("AZURE_OPENAI_DEPLOYMENT"),
    )
    inbox = GmailInbox()
    logger.info("Starting Gmail RFQ intake for configured mailbox.")
    while True:
        try:
            poll_once(inbox, extraction_agent)
        except Exception:
            logger.exception("Gmail inbox poll failed; the worker will retry after the configured interval.")
        time.sleep(interval)


if __name__ == "__main__":
    main()
