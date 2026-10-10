import math

from app.services.ml_prediction import MLPredictionService
from app.services.pricing_policy import validate_quote_policy


class QuoteSimulationService:

    def __init__(
        self,
        prediction_service: MLPredictionService
    ):
        self.prediction_service = prediction_service

    def simulate(
        self,
        bid: dict,
        proposed_quote_price: float,
        pricing_policy: dict | None = None
    ) -> dict:

        proposed_quote_price = float(proposed_quote_price)
        total_cost = float(bid["total_cost"])
        deal_size = float(bid["deal_size"])
        current_quote_price = float(bid["quote_price"])

        if not all(
            math.isfinite(value)
            for value in (
                proposed_quote_price,
                total_cost,
                deal_size,
                current_quote_price
            )
        ):
            raise ValueError(
                "Quote price, bid total cost, and deal size must be finite numbers."
            )

        if proposed_quote_price <= 0:
            raise ValueError(
                "Proposed quote price must be greater than zero."
            )

        if total_cost <= 0:
            raise ValueError(
                "Bid total cost must be greater than zero."
            )

        if deal_size <= 0:
            raise ValueError(
                "Bid deal size must be greater than zero."
            )

        if proposed_quote_price > deal_size:
            raise ValueError(
                "Proposed quote price cannot exceed the deal size."
            )

        margin_pct = (
            (proposed_quote_price - total_cost)
            / proposed_quote_price
            * 100
        )

        if margin_pct < 0:
            raise ValueError(
                "Proposed quote price cannot be below total cost."
            )

        if current_quote_price <= 0:
            raise ValueError(
                "Current quote price must be greater than zero."
            )

        discount_pct = (
            (current_quote_price - proposed_quote_price)
            / current_quote_price
            * 100
        )

        validate_quote_policy(
            margin_pct=margin_pct,
            discount_pct=discount_pct,
            pricing_policy=pricing_policy
        )

        quote_to_cost_ratio = (
            proposed_quote_price / total_cost
        )

        discount_amount = (
            current_quote_price - proposed_quote_price
        )

        deal_size_log = math.log1p(deal_size)

        features = {
            "total_cost": total_cost,
            "quote_price": proposed_quote_price,
            "discount_pct": discount_pct,
            "margin_pct": margin_pct,
            "deal_size": deal_size,
            "experience_years": bid["experience_years"],
            "product_unit_cost": bid["product_unit_cost"],
            "product_list_price": bid["product_list_price"],
            "quote_to_cost_ratio": quote_to_cost_ratio,
            "discount_amount": discount_amount,
            "deal_size_log": deal_size_log,
            "customer_prior_bids": bid["customer_prior_bids"],
            "customer_prior_wins": bid["customer_prior_wins"],
            "customer_prior_losses": bid["customer_prior_losses"],
            "customer_historical_win_rate": bid[
                "customer_historical_win_rate"
            ],
            "customer_avg_prior_deal_size": bid[
                "customer_avg_prior_deal_size"
            ],
            "customer_avg_prior_discount": bid[
                "customer_avg_prior_discount"
            ],
            "industry": bid["industry"],
            "country": bid["country"],
            "segment": bid["segment"],
            "product_category": bid["product_category"],
            "competitor_present": bid["competitor_present"]
        }

        win_probability = (
            self.prediction_service.predict_win_probability(
                features
            )
        )

        expected_profit = (
            proposed_quote_price - total_cost
        ) * win_probability

        return {
            "bid_id": bid["bid_id"],
            "current_quote_price": current_quote_price,
            "proposed_quote_price": proposed_quote_price,
            "discount_pct": discount_pct,
            "margin_pct": margin_pct,
            "win_probability": win_probability,
            "expected_profit": expected_profit,
            "status": "VALID",
            "validation_error": None
        }