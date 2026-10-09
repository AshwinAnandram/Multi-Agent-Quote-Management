import Copilot from "../components/Copilot";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PriceSimulator from "../components/PriceSimulator";

const API_BASE_URL = "http://127.0.0.1:8000";

function BidDetailPage() {
  const { bidId } = useParams();
  const navigate = useNavigate();

  const [bid, setBid] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function fetchBidDetail() {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/bids/${bidId}`
      );

      if (!response.ok) {
        throw new Error("Failed to load bid detail.");
      }

      const data = await response.json();
      setBid(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    fetchBidDetail();
  }, [bidId]);

  function formatCurrency(value) {
    if (value === null || value === undefined) {
      return "—";
    }

    return `$${Number(value).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })}`;
  }

  function formatPercent(value) {
    if (value === null || value === undefined) {
      return "—";
    }

    return `${Number(value).toFixed(2)}%`;
  }

  if (loading) {
    return (
      <main className="content">
        <div className="message">
          Loading bid...
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="content">
        <button
          className="back-button"
          onClick={() => navigate("/bids")}
        >
          ← Back to Bids
        </button>

        <div className="message error">
          {error}
        </div>
      </main>
    );
  }

  if (!bid) {
    return null;
  }

  return (
    <main className="content">
      <button
        className="back-button"
        onClick={() => navigate("/bids")}
      >
        ← Back to Bids
      </button>

      <div className="detail-header">
        <div>
          <h2>Bid {bid.bid_id}</h2>

          <p>
            {bid.customer_name} · {bid.industry} · {bid.country}
          </p>
        </div>

        <span className="detail-status">
          {bid.status}
        </span>
      </div>

      <div className="detail-section">
        <h3>Bid Information</h3>

        <div className="detail-table">
          <div className="detail-table-header bid-information-columns">
            <span>Bid Date</span>
            <span>Customer</span>
            <span>Industry</span>
            <span>Country</span>
            <span>Segment</span>
            <span>Deal Size</span>
            <span>Total Cost</span>
            <span>Competitor</span>
          </div>

          <div className="detail-table-row bid-information-columns">
            <span>{bid.bid_date}</span>
            <span>{bid.customer_name}</span>
            <span>{bid.industry}</span>
            <span>{bid.country}</span>
            <span>{bid.segment}</span>
            <span>{formatCurrency(bid.deal_size)}</span>
            <span>{formatCurrency(bid.total_cost)}</span>
            <span>
              {bid.competitor_present ? "Yes" : "No"}
            </span>
          </div>
        </div>
      </div>

      <div className="detail-section">
        <h3>Quote</h3>

        <div className="detail-table">
          <div className="detail-table-header quote-columns">
            <span>Original Quote</span>
            <span>Current Quote</span>
            <span>Current Discount</span>
            <span>Current Margin</span>
          </div>

          <div className="detail-table-row quote-columns">
            <span>
              {formatCurrency(bid.original_quote_price)}
            </span>

            <span>
              {formatCurrency(bid.current_quote_price)}
            </span>

            <span>
              {formatPercent(bid.current_discount_pct)}
            </span>

            <span>
              {formatPercent(bid.current_margin_pct)}
            </span>
          </div>
        </div>
      </div>

      <div className="detail-section">
        <h3>Line Items</h3>

        <div className="detail-table">
          <div className="detail-table-header line-item-columns">
            <span>Product</span>
            <span>Category</span>
            <span>Quantity</span>
            <span>Unit Cost</span>
            <span>Unit Price</span>
            <span>Line Revenue</span>
          </div>

          {bid.line_items?.map((item) => (
            <div
              className="detail-table-row line-item-columns"
              key={item.bid_line_item_id}
            >
              <span>{item.product_name}</span>
              <span>{item.category}</span>
              <span>{item.quantity}</span>
              <span>
                {formatCurrency(item.unit_cost)}
              </span>
              <span>
                {formatCurrency(item.unit_price)}
              </span>
              <span>
                {formatCurrency(item.line_revenue)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="detail-section">
        <h3>Quote History</h3>

        <div className="detail-table">
          <div className="detail-table-header quote-history-columns">
            <span>Version</span>
            <span>Quote Price</span>
            <span>Discount</span>
            <span>Margin</span>
            <span>Source</span>
            <span>Created By</span>
            <span>Created At</span>
            <span>Current</span>
          </div>

          {bid.quote_history?.map((quote) => (
            <div
              className="detail-table-row quote-history-columns"
              key={quote.quote_version_id}
            >
              <span>{quote.version_number}</span>

              <span>
                {formatCurrency(quote.quote_price)}
              </span>

              <span>
                {formatPercent(quote.discount_pct)}
              </span>

              <span>
                {formatPercent(quote.margin_pct)}
              </span>

              <span>{quote.source}</span>

              <span>
                {quote.created_by || "—"}
              </span>

              <span>
                {new Date(
                  quote.created_at
                ).toLocaleString("en-US")}
              </span>

              <span
                className={
                  quote.is_current
                    ? "quote-current"
                    : ""
                }
              >
                {quote.is_current ? "Current" : ""}
              </span>
            </div>
          ))}
        </div>
      </div>

      {bid.status === "OPEN" && (
        <PriceSimulator
        bid={bid}
        pricingPolicy={bid.pricing_policy}
        onPriceApplied={fetchBidDetail}
        />
      )}
    </main>
  );
}

export default BidDetailPage;