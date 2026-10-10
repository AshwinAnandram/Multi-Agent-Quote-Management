from app.services.pricing_policy import get_policy_limits
from app.services.quote_simulation import QuoteSimulationService


class QuoteOptimizationService:

    def __init__(
        self,
        simulation_service: QuoteSimulationService
    ):
        self.simulation_service = simulation_service

    def optimize(
        self,
        bid: dict,
        pricing_policy: dict,
        min_price: float | None = None,
        max_price: float | None = None,
        step: float = 1000.0,
        top_n: int = 1
    ) -> dict:

        total_cost = float(bid["total_cost"])
        deal_size = float(bid["deal_size"])
        min_margin_pct, max_discount_pct = get_policy_limits(
            pricing_policy
        )

        lower_bound = (
            total_cost
            if min_price is None
            else max(float(min_price), total_cost)
        )

        upper_bound = (
            deal_size
            if max_price is None
            else min(float(max_price), deal_size)
        )

        if lower_bound > upper_bound:
            raise ValueError(
                "Minimum price cannot exceed maximum price."
            )

        if step <= 0:
            raise ValueError(
                "Optimization step must be greater than zero."
            )

        if top_n < 1:
            raise ValueError(
                "Number of optimal prices must be at least one."
            )

        prices = []

        current_price = lower_bound

        while current_price <= upper_bound:
            prices.append(current_price)
            current_price += step

        if prices[-1] != upper_bound:
            prices.append(upper_bound)

        results = []
        rejected_count = 0

        for price in prices:

            try:
                result = self.simulation_service.simulate(
                    bid=bid,
                    proposed_quote_price=price,
                    pricing_policy=pricing_policy
                )

                results.append(result)

            except ValueError:
                rejected_count += 1

        if not results:
            raise ValueError(
                "No feasible quote prices were found "
                "within the optimization range and "
                "pricing policy constraints."
            )

        ranked_results = sorted(
            results,
            key=lambda result: result["expected_profit"],
            reverse=True,
        )[:top_n]

        optimal_result = ranked_results[0]

        return {
            "status": "COMPLETED",
            "optimization_target": "expected_profit",
            "pricing_policy": {
                "pricing_policy_id": pricing_policy[
                    "pricing_policy_id"
                ],
                "customer_id": pricing_policy[
                    "customer_id"
                ],
                "min_margin_pct": min_margin_pct,
                "max_discount_pct": max_discount_pct
            },
            "optimal_result": optimal_result,
            "optimal_results": ranked_results,
            "scenarios_evaluated": len(prices),
            "feasible_scenarios": len(results),
            "rejected_scenarios": rejected_count
        }