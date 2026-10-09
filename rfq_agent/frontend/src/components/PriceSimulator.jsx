import { useState } from "react";

const API_BASE_URL = "http://127.0.0.1:8000";

function PriceSimulator({ bid, pricingPolicy, onPriceApplied }) {
  const [proposedPrice, setProposedPrice] = useState("");
  const [simulation, setSimulation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [applying, setApplying] = useState(false);
  const [applyMessage, setApplyMessage] = useState(null);
  const isSameAsCurrentQuote = simulation && Number(simulation.proposed_quote_price) === Number(bid.current_quote_price);

  async function handleSimulate() {
    setLoading(true);
    setError(null);
    setSimulation(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/bids/${bid.bid_id}/simulate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            proposed_quote_price: Number(proposedPrice)
          })
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Simulation failed.");
      }

      setSimulation(data.simulation);

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

async function handleApplyPrice() {
  if (!simulation) {
    return;
  }

  setApplying(true);
  setError(null);
  setApplyMessage(null);

  try {
    const response = await fetch(
      `${API_BASE_URL}/bids/${bid.bid_id}/apply-price`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          proposed_quote_price: Number(proposedPrice),
          source: "SALES_REP",
          created_by: "TEST_USER"
        })
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Failed to apply price.");
    }

    setProposedPrice("");
    setSimulation(null);

    await onPriceApplied();

  } catch (err) {
    setError(err.message);
  } finally {
    setApplying(false);
  }
}

  return (
      <div className="detail-section">
        <h3>Pricing & Simulation</h3>

        {pricingPolicy && (
          <div className="pricing-policy">
            <h4>Pricing Policy</h4>

            <div className="pricing-policy-values">
              <div>
                <span>Minimum Margin: </span>
                <strong>
                  {Number(pricingPolicy.min_margin_pct).toFixed(2)}%
                </strong>
              </div>

              <div>
                <span>Maximum Discount: </span>
                <strong>
                  {Number(pricingPolicy.max_discount_pct).toFixed(2)}%
                </strong>
              </div>
            </div>
          </div>
        )}


      <div className="price-simulator">
        <div className="simulator-input">
          <label htmlFor="proposed-price">
            Proposed Quote Price:
          </label>

          <input
            id="proposed-price"
            type="number"
            min="0"
            step="0.01"
            value={proposedPrice}
            onChange={(event) =>
              setProposedPrice(event.target.value)
            }
          />

          <button
            onClick={handleSimulate}
            disabled={loading}
          >
            {loading ? "Simulating..." : "Simulate"}
          </button>
        </div>

        {error && (
          <div className="message error">
            {error}
          </div>
        )}

        {simulation && (
          <div className="simulation-results">
            <div>
              <span>Proposed Price: </span>
              <strong>
                ${Number(simulation.proposed_quote_price).toLocaleString(
                  "en-US",
                  {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  }
                )}
              </strong>
            </div>

            <div>
              <span>Discount: </span>
              <strong>
                {Number(simulation.discount_pct).toFixed(2)}%
              </strong>
            </div>

            <div>
              <span>Margin: </span>
              <strong>
                {Number(simulation.margin_pct).toFixed(2)}%
              </strong>
            </div>

            <div>
              <span>Win Probability: </span>
              <strong>
                {(Number(simulation.win_probability) * 100).toFixed(2)}%
              </strong>
            </div>

            <div>
              <span>Expected Profit: </span>
              <strong>
                ${Number(simulation.expected_profit).toLocaleString(
                  "en-US",
                  {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  }
                )}
              </strong>
            </div>
            {isSameAsCurrentQuote && (
              <div className="message">
                The evaluated quote is already the current quote price.
                There is no change to apply.
              </div>
            )}
            <button
              onClick={handleApplyPrice}
              disabled={
                applying ||
                !simulation ||
                isSameAsCurrentQuote
              }
            >
              {applying ? "Applying..." : "Apply Price"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default PriceSimulator;