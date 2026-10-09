from app.repositories.bid_repository import (
    get_bids,
    get_bid,
    get_bid_line_items,
    get_bid_simulation_context,
    get_customer_history,
    get_pricing_policy,
    get_current_quote_version,
    create_quote_version,
    get_quote_history
)

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