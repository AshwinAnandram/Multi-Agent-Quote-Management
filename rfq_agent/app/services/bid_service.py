from app.repositories.bid_repository import (
    get_bids,
    get_bid,
    get_bid_line_items,
    get_bid_simulation_context,
    get_customer_history,
    get_pricing_policy,
    get_current_quote_version,
    create_quote_version,
    get_quote_history,
    mark_bid_closed_if_open,
)
from app.repositories.bid_repository import get_bid_line_items
from app.services.gmail_client import GmailInbox


class BidFinalizationError(RuntimeError):
    pass

def list_bids(
    status: str = "OPEN",
    page: int = 1,
    page_size: int = 25
):
    return get_bids(
        status=status,
        page=page,
        page_size=page_size
    )

def get_bid_detail(bid_id: int):
    bid = get_bid(bid_id)

    if bid is None:
        return None

    bid["line_items"] = get_bid_line_items(bid_id)
    bid["quote_history"] = get_quote_history(bid_id)
    bid["pricing_policy"] = get_pricing_policy_data(
        bid["customer_id"]
    )
    return bid

def get_bid_simulation_context_data(bid_id: int):
    return get_bid_simulation_context(bid_id)

def get_customer_history_data(bid_id: int):
    return get_customer_history(bid_id)

def get_pricing_policy_data(customer_id: int):
    return get_pricing_policy(customer_id)


def finalize_open_bid(bid_id: int) -> dict:
    bid = get_bid(bid_id)
    if bid is None:
        raise LookupError(f"Bid {bid_id} was not found.")
    if bid["status"] != "OPEN":
        raise ValueError(f"Bid {bid_id} is not open for finalization.")
    recipient = (bid.get("sales_rep_email") or "").strip()
    if not recipient:
        raise ValueError("Add an email address to the assigned sales rep before finalizing this bid.")

    items = get_bid_line_items(bid_id)
    body = _bid_finalization_email_body(bid, items)
    subject = f"Bid {bid_id} finalized: {bid['customer_name']}"
    try:
        message_id = GmailInbox().send_message(recipient, subject, body)
    except Exception as error:
        raise BidFinalizationError(
            "The sales-rep email could not be sent. The bid remains open."
        ) from error

    if not mark_bid_closed_if_open(bid_id):
        raise BidFinalizationError(
            "The email was sent, but the bid status changed before it could be closed. Contact an administrator."
        )
    return {
        "bid_id": bid_id,
        "status": "CLOSED",
        "sales_rep_email": recipient,
        "email_message_id": message_id,
    }


def _bid_finalization_email_body(bid: dict, items: list[dict]) -> str:
    line_items = "\n".join(
        f"- {item['product_name']}: {item['quantity']} × {item['unit_price']}"
        for item in items
    ) or "- No line items recorded"
    return (
        f"Hello {bid.get('sales_rep_name') or 'Sales Representative'},\n\n"
        f"Bid {bid['bid_id']} has been finalized by the sales executive and is now CLOSED.\n\n"
        f"Customer: {bid['customer_name']}\n"
        f"Bid date: {bid.get('bid_date') or '—'}\n"
        f"Current quote: {bid.get('current_quote_price') or bid.get('original_quote_price') or '—'}\n"
        f"Deal size: {bid.get('deal_size') or '—'}\n\n"
        f"Line items:\n{line_items}\n"
    )
