from sqlalchemy import text

from app.db import engine
from app.services.bid_service import (
    get_bid_simulation_context_data,
    get_pricing_policy_data,
)
from app.services.quote_simulation import QuoteSimulationService


class RiskEvidenceService:
    def __init__(self, simulation_service: QuoteSimulationService):
        self.simulation_service = simulation_service

    def _get_deal_size_band(self, deal_size: float) -> dict:
        query = text("""
            SELECT
                deal_size_risk_band_id,
                band_name,
                min_deal_size,
                max_deal_size,
                min_deal_size_inclusive,
                max_deal_size_inclusive
            FROM deal_size_risk_bands
            WHERE
                (:deal_size > min_deal_size
                OR (:deal_size = min_deal_size AND min_deal_size_inclusive))
                AND
                (
                    max_deal_size IS NULL
                    OR :deal_size < max_deal_size
                    OR (:deal_size = max_deal_size AND max_deal_size_inclusive)
                )
            LIMIT 1
        """)

        with engine.connect() as connection:
            row = connection.execute(
                query,
                {"deal_size": deal_size},
            ).mappings().first()

        if not row:
            raise ValueError(
                f"No deal size risk band found for deal size {deal_size}"
            )

        return dict(row)

    def _get_margin_risk(
        self,
        margin_pct: float,
        min_margin_pct: float,
    ) -> str:
        if margin_pct > 50:
            return "LOW"

        if margin_pct >= min_margin_pct + 5:
            return "MEDIUM"

        return "HIGH"

    def _get_discount_risk(
        self,
        deal_size_risk_band_id: int,
        discount_pct: float,
    ) -> str:
        query = text("""
                        SELECT
                            risk_level
                        FROM discount_risk_rules
                        WHERE
                            deal_size_risk_band_id = :deal_size_risk_band_id
                            AND
                            (
                                :discount_pct > min_discount_pct
                                OR (
                                    :discount_pct = min_discount_pct
                                    AND min_discount_inclusive
                                )
                            )
                            AND
                            (
                                max_discount_pct IS NULL
                                OR :discount_pct < max_discount_pct
                                OR (
                                    :discount_pct = max_discount_pct
                                    AND max_discount_inclusive
                                )
                            )
                        LIMIT 1
                    """)

        with engine.connect() as connection:
            row = connection.execute(
                query,
                {
                    "deal_size_risk_band_id": deal_size_risk_band_id,
                    "discount_pct": discount_pct,
                },
            ).mappings().first()

        if not row:
            raise ValueError(
                f"No discount risk rule found for band "
                f"{deal_size_risk_band_id} and discount {discount_pct:.2f}%"
            )

        return row["risk_level"]

    def _get_win_probability_risk(
        self,
        win_probability: float,
    ) -> str:
        query = text("""
            SELECT
                risk_level
            FROM win_probability_risk_rules
            WHERE
                (
                    :probability > min_probability
                    OR (
                        :probability = min_probability
                        AND min_probability_inclusive
                    )
                )
                AND
                (
                    max_probability IS NULL
                    OR :probability < max_probability
                    OR (
                        :probability = max_probability
                        AND max_probability_inclusive
                    )
                )
            LIMIT 1
        """)

        with engine.connect() as connection:
            row = connection.execute(
                query,
                {"probability": win_probability},
            ).mappings().first()

        if not row:
            raise ValueError(
                f"No win probability risk rule found for "
                f"probability {win_probability}"
            )

        return row["risk_level"]

    def _get_overall_risk(
        self,
        deal_size_risk_band_id: int,
        win_probability_risk: str,
        margin_risk: str,
        discount_risk: str,
    ) -> str:
        query = text("""
            SELECT
                overall_risk
            FROM overall_risk_matrix
            WHERE
                deal_size_risk_band_id = :deal_size_risk_band_id
                AND win_probability_risk = :win_probability_risk
                AND margin_risk = :margin_risk
                AND discount_risk = :discount_risk
            LIMIT 1
        """)

        with engine.connect() as connection:
            row = connection.execute(
                query,
                {
                    "deal_size_risk_band_id": deal_size_risk_band_id,
                    "win_probability_risk": win_probability_risk,
                    "margin_risk": margin_risk,
                    "discount_risk": discount_risk,
                },
            ).mappings().first()

        if not row:
            raise ValueError(
                "No overall risk matrix rule found"
            )

        return row["overall_risk"]

    def evaluate(
        self,
        bid_id: int,
        proposed_quote_price: float | None = None,
    ) -> dict:
        bid = get_bid_simulation_context_data(bid_id)
        pricing_policy = get_pricing_policy_data(bid["customer_id"])

        if proposed_quote_price is None:
            proposed_quote_price = float(
                bid["quote_price"]
            )

        simulation = self.simulation_service.simulate(
            bid=bid,
            proposed_quote_price=proposed_quote_price,
            pricing_policy=pricing_policy,
        )

        deal_size = float(bid["deal_size"])
        margin_pct = float(simulation["margin_pct"])
        discount_pct = float(simulation["discount_pct"])
        win_probability = float(
            simulation["win_probability"]
        )

        min_margin_pct = float(
            pricing_policy["min_margin_pct"]
        )

        deal_size_band = self._get_deal_size_band(
            deal_size
        )

        margin_risk = self._get_margin_risk(
            margin_pct=margin_pct,
            min_margin_pct=min_margin_pct,
        )

        discount_risk = self._get_discount_risk(
            deal_size_risk_band_id=deal_size_band[
                "deal_size_risk_band_id"
            ],
            discount_pct=discount_pct,
        )

        win_probability_risk = self._get_win_probability_risk(
            win_probability=win_probability
        )

        overall_risk = self._get_overall_risk(
            deal_size_risk_band_id=deal_size_band[
                "deal_size_risk_band_id"
            ],
            win_probability_risk=win_probability_risk,
            margin_risk=margin_risk,
            discount_risk=discount_risk,
        )

        return {
            "bid_id": bid_id,
            "quote": {
                "current_quote_price": float(
                    bid["quote_price"]
                ),
                "proposed_quote_price": float(
                    proposed_quote_price
                ),
                "deal_size": deal_size,
                "margin_pct": margin_pct,
                "discount_pct": discount_pct,
                "win_probability": win_probability,
            },
            "deal_size_band": {
                "deal_size_risk_band_id": deal_size_band[
                    "deal_size_risk_band_id"
                ],
                "band_name": deal_size_band["band_name"],
                "min_deal_size": float(
                    deal_size_band["min_deal_size"]
                ),
                "max_deal_size": (
                    float(deal_size_band["max_deal_size"])
                    if deal_size_band["max_deal_size"] is not None
                    else None
                ),
            },
            "margin": {
                "margin_pct": margin_pct,
                "minimum_margin_pct": min_margin_pct,
                "risk": margin_risk,
            },
            "discount": {
                "discount_pct": discount_pct,
                "risk": discount_risk,
            },
            "win_probability": {
                "probability": win_probability,
                "risk": win_probability_risk,
            },
            "overall_risk": overall_risk,
        }