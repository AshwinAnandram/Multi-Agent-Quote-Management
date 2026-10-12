from sqlalchemy import text

from app.db import engine


def get_bids(
    status: str = "OPEN",
    page: int = 1,
    page_size: int = 25
):
    offset = (page - 1) * page_size

    count_query = text("""
        SELECT COUNT(*)
        FROM bids b
        WHERE (
            :status = 'ALL'
            OR b.status = :status
        )
    """)

    query = text("""
        SELECT
            b.bid_id,
            b.rfq_id,
            b.customer_id,
            c.customer_name,
            c.industry,
            c.country,
            b.bid_date,
            b.total_cost,
            qv.quote_price AS current_quote_price,
            qv.discount_pct AS current_discount_pct,
            qv.margin_pct AS current_margin_pct,
            b.deal_size,
            b.competitor_present,
            b.status,
            b.lost_reason,
            b.outcome_missing_fields
        FROM bids b
        JOIN customers c
            ON c.customer_id = b.customer_id
        LEFT JOIN quote_versions qv
            ON qv.bid_id = b.bid_id
            AND qv.is_current = TRUE
        WHERE (
            :status = 'ALL'
            OR b.status = :status
        )
        ORDER BY b.bid_date DESC, b.bid_id DESC
        LIMIT :limit
        OFFSET :offset
    """)

    with engine.connect() as connection:
        total = connection.execute(
            count_query,
            {
                "status": status
            }
        ).scalar_one()

        result = connection.execute(
            query,
            {
                "status": status,
                "limit": page_size,
                "offset": offset
            }
        )

        bids = [
            dict(row._mapping)
            for row in result
        ]

        return {
            "bids": bids,
            "total": total
        }

def get_bid(bid_id: int):
    query = text("""
        SELECT
            b.bid_id,
            b.rfq_id,
            b.customer_id,
            c.customer_name,
            c.industry,
            c.country,
            c.segment,
            b.bid_date,
            b.total_cost,
            b.quote_price AS original_quote_price,
            b.discount_pct AS original_discount_pct,
            b.margin_pct AS original_margin_pct,
            b.deal_size,
            b.competitor_present,
            b.competitor_price,
            b.days_to_quote,
            b.status,
            b.lost_reason,
            b.outcome_missing_fields,
            sr.sales_rep_name,
            sr.email AS sales_rep_email,
            qv.quote_version_id,
            qv.version_number AS current_quote_version,
            qv.quote_price AS current_quote_price,
            qv.discount_pct AS current_discount_pct,
            qv.margin_pct AS current_margin_pct,
            qv.source AS current_quote_source,
            qv.created_by AS current_quote_created_by,
            qv.created_at AS current_quote_created_at
        FROM bids b
        JOIN customers c
            ON c.customer_id = b.customer_id
        LEFT JOIN sales_reps sr
            ON sr.sales_rep_id = b.sales_rep_id
        LEFT JOIN quote_versions qv
            ON qv.bid_id = b.bid_id
            AND qv.is_current = TRUE
        WHERE b.bid_id = :bid_id
    """)
    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"bid_id": bid_id}
        )
        row = result.fetchone()
        if row is None:
            return None
        return dict(row._mapping)


def mark_bid_closed_if_open(bid_id: int) -> bool:
    with engine.begin() as connection:
        result = connection.execute(
            text("UPDATE bids SET status = 'CLOSED' WHERE bid_id = :bid_id AND status = 'OPEN'"),
            {"bid_id": bid_id},
        )
        return result.rowcount == 1


def apply_closed_bid_outcome(
    *,
    bid_id: int,
    status: str,
    source_message_id: str,
    final_quote_price: float | None,
    lost_reason: str | None,
    missing_fields: list[str],
) -> dict:
    """Apply an explicit customer outcome to one CLOSED bid, idempotently."""
    if status not in {"WON", "LOST"}:
        raise ValueError("Outcome status must be WON or LOST.")

    with engine.begin() as connection:
        duplicate = connection.execute(
            text("SELECT bid_id FROM bids WHERE outcome_source_message_id = :message_id"),
            {"message_id": source_message_id},
        ).scalar_one_or_none()
        if duplicate is not None:
            return {"matched": True, "duplicate": True, "bid_id": duplicate}

        row = connection.execute(
            text("""SELECT b.bid_id, b.status, b.total_cost, b.quote_price,
                          qv.quote_price AS current_quote_price
                   FROM bids b
                   LEFT JOIN quote_versions qv
                     ON qv.bid_id = b.bid_id AND qv.is_current = TRUE
                   WHERE b.bid_id = :bid_id
                   FOR UPDATE OF b"""),
            {"bid_id": bid_id},
        ).mappings().first()
        if row is None or row["status"] != "CLOSED":
            return {"matched": False, "duplicate": False, "bid_id": bid_id}

        if status == "WON" and final_quote_price is not None:
            reference_price = row["current_quote_price"] or row["quote_price"]
            total_cost = row["total_cost"]
            if reference_price is None or float(reference_price) <= 0 or total_cost is None:
                if "quote_metrics" not in missing_fields:
                    missing_fields.append("quote_metrics")
            else:
                discount_pct = (float(reference_price) - final_quote_price) / float(reference_price) * 100
                margin_pct = (final_quote_price - float(total_cost)) / final_quote_price * 100
                next_version = connection.execute(
                    text("SELECT COALESCE(MAX(version_number), 0) + 1 FROM quote_versions WHERE bid_id = :bid_id"),
                    {"bid_id": bid_id},
                ).scalar_one()
                connection.execute(
                    text("UPDATE quote_versions SET is_current = FALSE WHERE bid_id = :bid_id AND is_current = TRUE"),
                    {"bid_id": bid_id},
                )
                connection.execute(
                    text("""INSERT INTO quote_versions (
                               bid_id, version_number, quote_price, discount_pct,
                               margin_pct, source, created_by, is_current
                           ) VALUES (
                               :bid_id, :version_number, :quote_price, :discount_pct,
                               :margin_pct, 'CUSTOMER_OUTCOME', 'Customer email', TRUE
                           )"""),
                    {
                        "bid_id": bid_id,
                        "version_number": next_version,
                        "quote_price": final_quote_price,
                        "discount_pct": discount_pct,
                        "margin_pct": margin_pct,
                    },
                )

        result = connection.execute(
            text("""UPDATE bids
                   SET status = :status,
                       lost_reason = :lost_reason,
                       outcome_missing_fields = :missing_fields,
                       outcome_source_message_id = :message_id
                   WHERE bid_id = :bid_id AND status = 'CLOSED'"""),
            {
                "status": status,
                "lost_reason": lost_reason if status == "LOST" else None,
                "missing_fields": missing_fields,
                "message_id": source_message_id,
                "bid_id": bid_id,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError("Bid status changed while the outcome was being applied.")
        return {"matched": True, "duplicate": False, "bid_id": bid_id, "status": status}

def get_bid_line_items(bid_id: int):

    query = text("""
        SELECT
            bli.bid_line_item_id,
            bli.product_id,
            p.product_name,
            p.category,
            bli.quantity,
            bli.unit_cost,
            bli.unit_price,
            bli.line_cost,
            bli.line_revenue
        FROM bid_line_items bli
        JOIN products p
            ON p.product_id = bli.product_id
        WHERE bli.bid_id = :bid_id
        ORDER BY bli.bid_line_item_id
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"bid_id": bid_id}
        )

        return [
            dict(row._mapping)
            for row in result
        ]

def get_bid_simulation_context(bid_id: int):
    query = text("""
        SELECT
            b.bid_id,
            b.customer_id,
            b.total_cost,
            COALESCE(qv.quote_price, b.quote_price) AS quote_price,
            b.discount_pct,
            b.margin_pct,
            b.deal_size,
            sr.experience_years,
            p.unit_cost AS product_unit_cost,
            p.list_price AS product_list_price,
            ch.customer_prior_bids,
            ch.customer_prior_wins,
            ch.customer_prior_losses,
            ch.customer_historical_win_rate,
            ch.customer_avg_prior_deal_size,
            ch.customer_avg_prior_discount,
            c.industry,
            c.country,
            c.segment,
            p.category AS product_category,
            b.competitor_present
        FROM bids b
        JOIN customers c
            ON c.customer_id = b.customer_id
        JOIN sales_reps sr
            ON sr.sales_rep_id = b.sales_rep_id
        JOIN bid_line_items bli
            ON bli.bid_id = b.bid_id
        JOIN products p
            ON p.product_id = bli.product_id
        LEFT JOIN bid_customer_history ch
            ON ch.bid_id = b.bid_id
        LEFT JOIN quote_versions qv
            ON qv.bid_id = b.bid_id
            AND qv.is_current = TRUE
        WHERE b.bid_id = :bid_id
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"bid_id": bid_id}
        )

        row = result.fetchone()

        if row is None:
            return None

        return dict(row._mapping)


def get_customer_history(bid_id: int):
    query = text("""
        SELECT
            b.bid_id,
            b.customer_id,
            h.customer_prior_bids,
            h.customer_prior_wins,
            h.customer_prior_losses,
            h.customer_historical_win_rate,
            h.customer_avg_prior_deal_size,
            h.customer_avg_prior_discount
        FROM bids b
        LEFT JOIN LATERAL (
            SELECT
                customer_prior_bids,
                customer_prior_wins,
                customer_prior_losses,
                customer_historical_win_rate,
                customer_avg_prior_deal_size,
                customer_avg_prior_discount
            FROM bid_customer_history
            WHERE customer_id = b.customer_id
              AND bid_date < b.bid_date
            ORDER BY bid_date DESC, bid_id DESC
            LIMIT 1
        ) h ON TRUE
        WHERE b.bid_id = :bid_id
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"bid_id": bid_id}
        )

        row = result.fetchone()

        if row is None:
            return None

        return dict(row._mapping)

def get_pricing_policy(customer_id: int):
    with engine.connect() as connection:
        return get_pricing_policy_in_connection(connection, customer_id)


def get_pricing_policy_in_connection(connection, customer_id: int):
    query = text("""
        SELECT
            pricing_policy_id,
            customer_id,
            min_margin_pct,
            max_discount_pct,
            is_active
        FROM pricing_policies
        WHERE is_active = TRUE
          AND (
              customer_id = :customer_id
              OR customer_id IS NULL
          )
        ORDER BY
            CASE
                WHEN customer_id = :customer_id THEN 0
                WHEN customer_id IS NULL THEN 1
            END
        LIMIT 1
    """)

    row = connection.execute(
        query,
        {"customer_id": customer_id}
    ).fetchone()
    return dict(row._mapping) if row is not None else None

def get_current_quote_version(bid_id: int):
    query = text("""
        SELECT
            quote_version_id,
            bid_id,
            version_number,
            quote_price,
            discount_pct,
            margin_pct,
            source,
            created_by,
            created_at,
            is_current
        FROM quote_versions
        WHERE bid_id = :bid_id
          AND is_current = TRUE
        LIMIT 1
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"bid_id": bid_id}
        )
        row = result.fetchone()

        if row is None:
            return None

        return dict(row._mapping)

def create_quote_version(
    bid_id: int,
    quote_price: float,
    discount_pct: float,
    margin_pct: float,
    source: str,
    created_by: str
):
    with engine.begin() as connection:

        connection.execute(
            text("""
                SELECT bid_id
                FROM bids
                WHERE bid_id = :bid_id
                FOR UPDATE
            """),
            {"bid_id": bid_id}
        )

        result = connection.execute(
            text("""
                SELECT
                    COALESCE(MAX(version_number), 0) + 1 AS next_version
                FROM quote_versions
                WHERE bid_id = :bid_id
            """),
            {"bid_id": bid_id}
        )

        next_version = result.scalar_one()

        connection.execute(
            text("""
                UPDATE quote_versions
                SET is_current = FALSE
                WHERE bid_id = :bid_id
                  AND is_current = TRUE
            """),
            {"bid_id": bid_id}
        )

        result = connection.execute(
            text("""
                INSERT INTO quote_versions (
                    bid_id,
                    version_number,
                    quote_price,
                    discount_pct,
                    margin_pct,
                    source,
                    created_by,
                    is_current
                )
                VALUES (
                    :bid_id,
                    :version_number,
                    :quote_price,
                    :discount_pct,
                    :margin_pct,
                    :source,
                    :created_by,
                    TRUE
                )
                RETURNING
                    quote_version_id,
                    bid_id,
                    version_number,
                    quote_price,
                    discount_pct,
                    margin_pct,
                    source,
                    created_by,
                    created_at,
                    is_current
            """),
            {
                "bid_id": bid_id,
                "version_number": next_version,
                "quote_price": quote_price,
                "discount_pct": discount_pct,
                "margin_pct": margin_pct,
                "source": source,
                "created_by": created_by
            }
        )

        row = result.fetchone()

        return dict(row._mapping)

def get_quote_history(bid_id: int):
    query = text("""
        SELECT
            quote_version_id,
            bid_id,
            version_number,
            quote_price,
            discount_pct,
            margin_pct,
            source,
            created_by,
            created_at,
            is_current
        FROM quote_versions
        WHERE bid_id = :bid_id
        ORDER BY version_number ASC
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"bid_id": bid_id}
        )

        return [
            dict(row._mapping)
            for row in result
        ]
