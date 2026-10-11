"""Persistence for inbound RFQs, using the existing RFQ and bid tables."""

import json

from sqlalchemy import text

from app.db import engine
from app.repositories.bid_repository import get_pricing_policy_in_connection
from app.services.pricing_policy import evaluate_quote_policy


def save_inbound_rfq(email, intake: dict) -> dict:
    """Save an inbound request once; source_email stays unset because its
    meaning is undocumented in the existing schema. The complete message
    envelope and extracted content are retained in extracted_json instead.
    """
    merged = intake["merged"]
    envelope = {
        "provider": email.provider,
        "mailbox": email.mailbox,
        "message_id": email.message_id,
        "sender": email.sender,
        "subject": email.subject,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "body": email.body,
        "attachments": intake["attachments"],
        "intake": intake,
    }
    rfq = merged.get("rfq") or {}
    received_date = email.received_at.date().isoformat() if email.received_at else None
    required_by_date = _date_or_none(rfq.get("required_by_date"))
    description = rfq.get("subject") or email.subject or "Email RFQ"

    with engine.begin() as connection:
        lock_key = f"rfq-intake:{email.source_message_id}"
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": lock_key},
        )
        existing = connection.execute(
            text("""SELECT rfq_id, processing_status FROM rfqs
                   WHERE source_message_id = :source_message_id LIMIT 1"""),
            {"source_message_id": email.source_message_id},
        ).mappings().first()
        if existing:
            return {"duplicate": True, **dict(existing)}

        row = connection.execute(
            text("""INSERT INTO rfqs (
                       received_date, required_by_date, delivery_location,
                       currency, payment_terms, rfq_description,
                       source_message_id, extracted_json, processing_status
                   ) VALUES (
                       :received_date, :required_by_date, :delivery_location,
                       :currency, :payment_terms, :rfq_description,
                       :source_message_id, CAST(:extracted_json AS jsonb), 'ON_HOLD'
                   ) RETURNING rfq_id, processing_status"""),
            {
                "received_date": received_date,
                "required_by_date": required_by_date,
                "delivery_location": rfq.get("delivery_location"),
                "currency": rfq.get("currency"),
                "payment_terms": rfq.get("payment_terms"),
                "rfq_description": description,
                "source_message_id": email.source_message_id,
                "extracted_json": json.dumps(envelope),
            },
        ).mappings().one()

        for item in merged.get("line_items") or []:
            connection.execute(
                text("""INSERT INTO rfq_line_items (
                           rfq_id, product_name_raw, quantity, unit, requirements
                       ) VALUES (
                           :rfq_id, :product_name_raw, :quantity, :unit, :requirements
                       )"""),
                {
                    "rfq_id": row["rfq_id"],
                    "product_name_raw": item.get("product_name"),
                    "quantity": item.get("quantity"),
                    "unit": item.get("unit"),
                    "requirements": item.get("requirements"),
                },
            )
        return {"duplicate": False, **dict(row)}


def list_on_hold_rfqs(page: int = 1, page_size: int = 25) -> dict:
    offset = (page - 1) * page_size
    with engine.connect() as connection:
        total = connection.execute(
            text("SELECT COUNT(*) FROM rfqs WHERE processing_status = 'ON_HOLD'")
        ).scalar_one()
        rows = connection.execute(
            text("""SELECT r.rfq_id, r.received_date, r.required_by_date,
                          r.delivery_location, r.rfq_description, r.processing_status,
                          r.extracted_json,
                          (SELECT COALESCE(json_agg(json_build_object(
                              'product_name', ri.product_name_raw,
                              'quantity', ri.quantity,
                              'unit', ri.unit
                          )), '[]'::json)
                           FROM rfq_line_items ri WHERE ri.rfq_id = r.rfq_id) AS line_items
                   FROM rfqs r
                   WHERE r.processing_status = 'ON_HOLD'
                   ORDER BY r.received_date DESC NULLS LAST, r.rfq_id DESC
                   LIMIT :limit OFFSET :offset"""),
            {"limit": page_size, "offset": offset},
        ).mappings().all()
        customer_names = {
            " ".join(name.split()).casefold()
            for name in connection.execute(text("SELECT customer_name FROM customers")).scalars()
            if name
        }
    return {
        "total": total,
        "rfqs": [
            {
                **_on_hold_rfq_fields(row, customer_names),
            }
            for row in rows
        ],
    }


def _on_hold_rfq_fields(row, customer_names: set[str]) -> dict:
    payload = row["extracted_json"] or {}
    intake = payload.get("intake") or {}
    merged = intake.get("merged") or {}
    customer_name = (merged.get("customer") or {}).get("name")
    normalized_name = " ".join(customer_name.split()).casefold() if customer_name else ""
    return {
        "rfq_id": row["rfq_id"],
        "received_date": row["received_date"],
        "required_by_date": row["required_by_date"],
        "delivery_location": row["delivery_location"],
        "rfq_description": row["rfq_description"],
        "processing_status": row["processing_status"],
        "sender": payload.get("sender"),
        "customer_name": customer_name,
        "customer_exists": bool(normalized_name and normalized_name in customer_names),
        "line_items": row["line_items"] or [],
        "review_reasons": intake.get("review_reasons") or [],
    }


def get_rfq_review(rfq_id: int) -> dict | None:
    with engine.connect() as connection:
        rfq = connection.execute(
            text("""SELECT rfq_id, customer_id, received_date, required_by_date,
                          delivery_location, currency, payment_terms, rfq_description,
                          source_message_id, extracted_json, processing_status
                   FROM rfqs WHERE rfq_id = :rfq_id"""),
            {"rfq_id": rfq_id},
        ).mappings().first()
        if not rfq:
            return None
        items = connection.execute(
            text("""SELECT ri.rfq_line_item_id, ri.product_name_raw, ri.product_id,
                          ri.quantity, ri.unit, ri.requirements,
                          p.product_name AS mapped_product_name
                   FROM rfq_line_items ri
                   LEFT JOIN products p ON p.product_id = ri.product_id
                   WHERE ri.rfq_id = :rfq_id ORDER BY ri.rfq_line_item_id"""),
            {"rfq_id": rfq_id},
        ).mappings().all()
        return {**dict(rfq), "line_items": [dict(item) for item in items]}


def get_review_options() -> dict:
    with engine.connect() as connection:
        customers = connection.execute(text(
            "SELECT customer_id, customer_name FROM customers ORDER BY customer_name"
        )).mappings().all()
        products = connection.execute(text(
            "SELECT product_id, product_name, category, unit_cost, list_price FROM products ORDER BY product_name"
        )).mappings().all()
        sales_reps = connection.execute(text(
            "SELECT sales_rep_id, sales_rep_name, region FROM sales_reps ORDER BY sales_rep_name"
        )).mappings().all()
    return {
        "customers": [dict(row) for row in customers],
        "products": [dict(row) for row in products],
        "sales_reps": [dict(row) for row in sales_reps],
    }


def create_or_find_customer(
    customer_name: str,
    industry: str | None = None,
    country: str | None = None,
    segment: str | None = None,
    min_margin_pct: float | None = None,
    max_discount_pct: float | None = None,
) -> dict:
    """Create a customer and optional active customer policy atomically."""
    normalized_name = " ".join(customer_name.split())
    if not normalized_name:
        raise ValueError("Customer name is required.")
    if (min_margin_pct is None) != (max_discount_pct is None):
        raise ValueError("Enter both custom policy limits, or leave both blank to use the global policy.")
    if min_margin_pct is not None and not 0 <= min_margin_pct <= 100:
        raise ValueError("Minimum margin must be between 0 and 100 percent.")
    if max_discount_pct is not None and not 0 <= max_discount_pct <= 100:
        raise ValueError("Maximum discount must be between 0 and 100 percent.")
    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"customer-name:{normalized_name.casefold()}"},
        )
        matches = connection.execute(
            text("""SELECT customer_id, customer_name FROM customers
                   WHERE lower(customer_name) = lower(:customer_name)
                   ORDER BY customer_id LIMIT 2"""),
            {"customer_name": normalized_name},
        ).mappings().all()
        if len(matches) > 1:
            raise ValueError("Multiple customers already use this name. Select one from the customer list.")
        if matches:
            return {**dict(matches[0]), "created": False, "policy_mode": "EXISTING_POLICY_UNCHANGED"}
        row = connection.execute(
            text("""INSERT INTO customers (customer_name, industry, country, segment)
                   VALUES (:customer_name, :industry, :country, :segment)
                   RETURNING customer_id, customer_name"""),
            {
                "customer_name": normalized_name,
                "industry": industry,
                "country": country,
                "segment": segment,
            },
        ).mappings().one()
        policy_mode = "GLOBAL_DEFAULT"
        if min_margin_pct is not None:
            policy = connection.execute(
                text("""INSERT INTO pricing_policies (
                           customer_id, min_margin_pct, max_discount_pct,
                           is_active, created_at, updated_at
                       ) VALUES (
                           :customer_id, :min_margin_pct, :max_discount_pct,
                           TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                       ) RETURNING pricing_policy_id"""),
                {
                    "customer_id": row["customer_id"],
                    "min_margin_pct": min_margin_pct,
                    "max_discount_pct": max_discount_pct,
                },
            ).mappings().one()
            policy_mode = "CUSTOMER_SPECIFIC"
        return {
            **dict(row),
            "created": True,
            "policy_mode": policy_mode,
            "pricing_policy_id": policy["pricing_policy_id"] if min_margin_pct is not None else None,
        }


def save_rfq_review(
    rfq_id: int,
    customer_id: int | None,
    values: dict,
    line_items: list[dict],
) -> None:
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT processing_status FROM rfqs WHERE rfq_id = :rfq_id FOR UPDATE"),
            {"rfq_id": rfq_id},
        ).mappings().first()
        if not row:
            raise LookupError("RFQ not found.")
        if row["processing_status"] not in {"ON_HOLD", "EXTRACTED"}:
            raise ValueError("This RFQ is no longer on hold.")
        connection.execute(
            text("""UPDATE rfqs
                   SET customer_id = :customer_id,
                       delivery_location = :delivery_location,
                       required_by_date = :required_by_date,
                       currency = :currency,
                       payment_terms = :payment_terms,
                       rfq_description = :rfq_description,
                       extracted_json = jsonb_set(
                           COALESCE(extracted_json, '{}'::jsonb),
                           '{review_values}', CAST(:review_values AS jsonb), TRUE
                       )
                   WHERE rfq_id = :rfq_id"""),
            {
                "customer_id": customer_id,
                **values,
                "review_values": json.dumps(values),
                "rfq_id": rfq_id,
            },
        )
        for item in line_items:
            if item.get("line_item_id") is None:
                connection.execute(
                    text("""INSERT INTO rfq_line_items (
                               rfq_id, product_name_raw, product_id, quantity, unit, requirements
                           ) VALUES (
                               :rfq_id, :product_name_raw, :product_id, :quantity, :unit, :requirements
                           )"""),
                    {
                        "rfq_id": rfq_id,
                        "product_name_raw": item.get("product_name_raw"),
                        "product_id": item.get("product_id"),
                        "quantity": item.get("quantity"),
                        "unit": item.get("unit"),
                        "requirements": item.get("requirements"),
                    },
                )
                continue
            result = connection.execute(
                text("""UPDATE rfq_line_items
                       SET product_name_raw = :product_name_raw,
                           product_id = :product_id,
                           quantity = :quantity,
                           unit = :unit,
                           requirements = :requirements
                       WHERE rfq_line_item_id = :line_item_id AND rfq_id = :rfq_id"""),
                {
                    **item,
                    "rfq_id": rfq_id,
                },
            )
            if result.rowcount != 1:
                raise ValueError(f"RFQ line item {item['line_item_id']} was not found.")


def reject_rfq(rfq_id: int, reason: str) -> bool:
    with engine.begin() as connection:
        result = connection.execute(
            text("""UPDATE rfqs SET processing_status = 'REJECTED'
                   WHERE rfq_id = :rfq_id AND processing_status IN ('ON_HOLD', 'EXTRACTED')"""),
            {"rfq_id": rfq_id},
        )
        if result.rowcount:
            connection.execute(
                text("""UPDATE rfqs
                       SET extracted_json = jsonb_set(
                           COALESCE(extracted_json, '{}'::jsonb),
                           '{review_decision}', CAST(:decision AS jsonb), TRUE
                       ) WHERE rfq_id = :rfq_id"""),
                {"rfq_id": rfq_id, "decision": json.dumps({"status": "REJECTED", "reason": reason})},
            )
        return result.rowcount == 1


class RFQAcceptanceError(ValueError):
    def __init__(self, message: str, decision: dict | None = None):
        super().__init__(message)
        self.decision = decision


def accept_rfq(rfq_id: int, confirm_source_conflicts: bool) -> dict:
    """Create an open bid only after catalog and active-policy checks pass."""
    with engine.begin() as connection:
        rfq = connection.execute(
            text("""SELECT rfq_id, customer_id, extracted_json, processing_status
                   FROM rfqs WHERE rfq_id = :rfq_id FOR UPDATE"""),
            {"rfq_id": rfq_id},
        ).mappings().first()
        if not rfq:
            raise LookupError("RFQ not found.")
        if rfq["processing_status"] not in {"ON_HOLD", "EXTRACTED"}:
            raise RFQAcceptanceError("This RFQ is no longer on hold.")
        existing_bid = connection.execute(
            text("SELECT bid_id FROM bids WHERE rfq_id = :rfq_id LIMIT 1"),
            {"rfq_id": rfq_id},
        ).scalar_one_or_none()
        if existing_bid:
            raise RFQAcceptanceError("A bid already exists for this RFQ.")

        envelope = rfq["extracted_json"] or {}
        intake = envelope.get("intake") or {}
        conflicts = intake.get("conflicts") or []
        if conflicts and not confirm_source_conflicts:
            raise RFQAcceptanceError(
                "Review and confirm the conflicting email and attachment values before accepting."
            )

        review = envelope.get("review_values") or {}
        customer_id = rfq["customer_id"]
        sales_rep_id = review.get("sales_rep_id")
        quote_price = review.get("opening_quote_price")
        deal_size = review.get("deal_size") or quote_price
        if not customer_id:
            raise RFQAcceptanceError("Select or create a customer before accepting.")
        if not sales_rep_id:
            raise RFQAcceptanceError("Select a sales executive before accepting.")
        if quote_price is None or float(quote_price) <= 0:
            raise RFQAcceptanceError("Enter a positive opening quote price before accepting.")
        quote_price = float(quote_price)
        if deal_size is None or float(deal_size) <= 0:
            raise RFQAcceptanceError("Deal size must be positive.")
        deal_size = float(deal_size)
        if quote_price > deal_size:
            raise RFQAcceptanceError("Opening quote price cannot exceed deal size.")

        sales_rep = connection.execute(
            text("SELECT sales_rep_id, sales_rep_name FROM sales_reps WHERE sales_rep_id = :id"),
            {"id": sales_rep_id},
        ).mappings().first()
        if not sales_rep:
            raise RFQAcceptanceError("The selected sales executive was not found.")

        line_items = connection.execute(
            text("""SELECT ri.rfq_line_item_id, ri.product_id, ri.product_name_raw,
                          ri.quantity, ri.unit, ri.requirements,
                          p.product_name, p.unit_cost, p.list_price
                   FROM rfq_line_items ri
                   LEFT JOIN products p ON p.product_id = ri.product_id
                   WHERE ri.rfq_id = :rfq_id
                   ORDER BY ri.rfq_line_item_id
                   FOR UPDATE OF ri"""),
            {"rfq_id": rfq_id},
        ).mappings().all()
        if not line_items:
            raise RFQAcceptanceError("Add at least one requested catalog item before accepting.")

        total_cost = 0.0
        list_price_total = 0.0
        normalized_lines = []
        for item in line_items:
            if item["product_id"] is None:
                raise RFQAcceptanceError(f"Map '{item['product_name_raw'] or 'an RFQ item'}' to a catalog product.")
            if item["quantity"] is None or float(item["quantity"]) <= 0:
                raise RFQAcceptanceError(f"Enter a positive quantity for '{item['product_name_raw'] or item['product_name']}'.")
            quantity = float(item["quantity"])
            if not quantity.is_integer():
                raise RFQAcceptanceError(
                    f"Quantity for '{item['product_name_raw'] or item['product_name']}' must be a whole number for bid creation."
                )
            quantity = int(quantity)
            if item["unit_cost"] is None or float(item["unit_cost"]) < 0:
                raise RFQAcceptanceError(f"Catalog cost is missing for '{item['product_name']}'.")
            if item["list_price"] is None or float(item["list_price"]) <= 0:
                raise RFQAcceptanceError(f"Catalog list price is missing for '{item['product_name']}'.")
            line_cost = float(item["unit_cost"]) * quantity
            line_list_price = float(item["list_price"]) * quantity
            total_cost += line_cost
            list_price_total += line_list_price
            normalized_lines.append({
                "product_id": item["product_id"],
                "quantity": quantity,
                "unit_cost": float(item["unit_cost"]),
                "line_cost": line_cost,
                "line_list_price": line_list_price,
            })

        if total_cost <= 0:
            raise RFQAcceptanceError("Mapped catalog items must have a positive total cost.")
        margin_pct = (quote_price - total_cost) / quote_price * 100
        discount_pct = (list_price_total - quote_price) / list_price_total * 100
        decision = evaluate_quote_policy(
            {"margin_pct": margin_pct, "discount_pct": discount_pct},
            get_pricing_policy_in_connection(connection, customer_id),
        )
        if decision["status"] != "COMPLIANT":
            raise RFQAcceptanceError(
                "; ".join(decision.get("reasons", [])) or "No applicable complete pricing policy was found.",
                decision=decision,
            )

        bid = connection.execute(
            text("""INSERT INTO bids (
                       rfq_id, customer_id, sales_rep_id, bid_date, total_cost,
                       quote_price, discount_pct, margin_pct, deal_size, status
                   ) VALUES (
                       :rfq_id, :customer_id, :sales_rep_id, CURRENT_DATE, :total_cost,
                       :quote_price, :discount_pct, :margin_pct, :deal_size, 'OPEN'
                   ) RETURNING bid_id"""),
            {
                "rfq_id": rfq_id,
                "customer_id": customer_id,
                "sales_rep_id": sales_rep_id,
                "total_cost": total_cost,
                "quote_price": quote_price,
                "discount_pct": discount_pct,
                "margin_pct": margin_pct,
                "deal_size": deal_size,
            },
        ).mappings().one()
        bid_id = bid["bid_id"]

        remaining_revenue = quote_price
        for index, item in enumerate(normalized_lines):
            if index == len(normalized_lines) - 1:
                line_revenue = remaining_revenue
            else:
                line_revenue = quote_price * item["line_list_price"] / list_price_total
                remaining_revenue -= line_revenue
            unit_price = line_revenue / item["quantity"]
            connection.execute(
                text("""INSERT INTO bid_line_items (
                           bid_id, product_id, quantity, unit_cost, unit_price,
                           line_cost, line_revenue
                       ) VALUES (
                           :bid_id, :product_id, :quantity, :unit_cost, :unit_price,
                           :line_cost, :line_revenue
                       )"""),
                {"bid_id": bid_id, **item, "unit_price": unit_price, "line_revenue": line_revenue},
            )

        connection.execute(
            text("""INSERT INTO quote_versions (
                       bid_id, version_number, quote_price, discount_pct, margin_pct,
                       source, created_by, is_current
                   ) VALUES (
                       :bid_id, 1, :quote_price, :discount_pct, :margin_pct,
                       'EMAIL_INTAKE', :created_by, TRUE
                   )"""),
            {
                "bid_id": bid_id,
                "quote_price": quote_price,
                "discount_pct": discount_pct,
                "margin_pct": margin_pct,
                "created_by": sales_rep["sales_rep_name"],
            },
        )
        connection.execute(
            text("""UPDATE rfqs SET processing_status = 'ACCEPTED',
                   extracted_json = jsonb_set(
                       COALESCE(extracted_json, '{}'::jsonb),
                       '{review_decision}', CAST(:decision AS jsonb), TRUE
                   ) WHERE rfq_id = :rfq_id"""),
            {
                "rfq_id": rfq_id,
                "decision": json.dumps({
                    "status": "ACCEPTED",
                    "bid_id": bid_id,
                    "pricing_policy": decision,
                    "discount_baseline": "mapped_catalog_list_price_total",
                    "discount_baseline_amount": list_price_total,
                }),
            },
        )
        return {
            "rfq_id": rfq_id,
            "bid_id": bid_id,
            "status": "OPEN",
            "quote_price": quote_price,
            "deal_size": deal_size,
            "total_cost": total_cost,
            "margin_pct": margin_pct,
            "discount_pct": discount_pct,
            "discount_baseline_amount": list_price_total,
            "pricing_policy": decision,
        }


def _date_or_none(value):
    if not value:
        return None
    from datetime import date

    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None
