import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

const API_BASE_URL = "http://127.0.0.1:8000";

function BidListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [status, setStatus] = useState("OPEN");
  const [showOnHold, setShowOnHold] = useState(searchParams.get("tab") === "on-hold");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const [bids, setBids] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchBids() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `${API_BASE_URL}/bids?status=${status}&page=${page}&page_size=${pageSize}`
        );

        if (!response.ok) {
          throw new Error("Failed to load bids.");
        }

        const data = await response.json();

        setBids(data.bids);
        setTotal(data.total);
        setTotalPages(data.total_pages);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchBids();
  }, [status, page, pageSize]);

  function handleStatusChange(newStatus) {
    setShowOnHold(false);
    setSearchParams({}, { replace: true });
    setStatus(newStatus);
    setPage(1);
  }

  function handleOnHoldChange() {
    setShowOnHold(true);
    setSearchParams({ tab: "on-hold" }, { replace: true });
  }

  function handlePageSizeChange(event) {
    setPageSize(Number(event.target.value));
    setPage(1);
  }

  function goToPreviousPage() {
    if (page > 1) {
      setPage(page - 1);
    }
  }

  function goToNextPage() {
    if (page < totalPages) {
      setPage(page + 1);
    }
  }

  const firstRecord =
    total === 0
      ? 0
      : (page - 1) * pageSize + 1;

  const lastRecord = Math.min(page * pageSize, total);

  return (
    <main className="content">
      <div className="page-header">
        <h2>Bids</h2>

        <div className="status-filter">
          <button
            className={showOnHold ? "active" : ""}
            onClick={handleOnHoldChange}
          >
            On Hold
          </button>
          <button
            className={!showOnHold && status === "OPEN" ? "active" : ""}
            onClick={() => handleStatusChange("OPEN")}
          >
            Open
          </button>

          <button
            className={!showOnHold && status === "CLOSED" ? "active" : ""}
            onClick={() => handleStatusChange("CLOSED")}
          >
            Closed
          </button>

          <button
            className={!showOnHold && status === "ALL" ? "active" : ""}
            onClick={() => handleStatusChange("ALL")}
          >
            All
          </button>
        </div>
      </div>

      {showOnHold ? (
        <OnHoldBids />
      ) : (
        <>
      <div className="list-controls">
        <div className="page-size-selector">
          <label htmlFor="page-size">
            Rows per page:
          </label>

          <select
            id="page-size"
            value={pageSize}
            onChange={handlePageSizeChange}
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>

        <div className="pagination-summary">
          Showing {firstRecord}–{lastRecord} of {total}
        </div>
      </div>

      {loading && (
        <div className="message">
          Loading bids...
        </div>
      )}

      {error && (
        <div className="message error">
          {error}
        </div>
      )}

      {!loading && !error && (
        <>
          <div className="bid-table">
            <div className="table-header">
              <span>Bid ID</span>
              <span>Customer</span>
              <span>Industry</span>
              <span>Bid Date</span>
              <span>Current Quote</span>
              <span>Margin</span>
              <span>Status</span>
            </div>

            {bids.map((bid) => (
              <div
                className="table-row"
                key={bid.bid_id}
              >
                <span
                  className="bid-link"
                  onClick={() => navigate(`/bids/${bid.bid_id}`)}
                >
                  {bid.bid_id}
                </span>

                <span>{bid.customer_name}</span>
                <span>{bid.industry}</span>
                <span>{bid.bid_date}</span>

                <span>
                  $
                  {Number(
                    bid.current_quote_price
                  ).toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  })}
                </span>

                <span>
                  {Number(
                    bid.current_margin_pct
                  ).toFixed(2)}
                  %
                </span>

                <span className="status-open">
                  {bid.status}
                </span>
              </div>
            ))}

            {bids.length === 0 && (
              <div className="empty-state">
                No bids found.
              </div>
            )}
          </div>

          <div className="pagination">
            <button
              onClick={goToPreviousPage}
              disabled={page === 1}
            >
              Previous
            </button>

            <span>
              Page {page} of {totalPages}
            </span>

            <button
              onClick={goToNextPage}
              disabled={
                page === totalPages ||
                totalPages === 0
              }
            >
              Next
            </button>
          </div>
        </>
      )}
        </>
      )}
    </main>
  );
}

function OnHoldBids() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/rfqs/on-hold`)
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load held RFQs.");
        return response.json();
      })
      .then((data) => setItems(data.rfqs))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="message">Loading held RFQs...</div>;
  if (error) return <div className="message error">{error}</div>;

  return (
    <section className="on-hold-list">
      <p>Requests that need an executive review before they become open bids.</p>
      {items.length === 0 ? (
        <div className="empty-state">No RFQs on hold</div>
      ) : items.map((item) => (
        <article className="on-hold-card" key={item.rfq_id}>
          <header className="on-hold-card-header">
            <strong>RFQ {item.rfq_id}</strong>
            <span>{item.processing_status}</span>
          </header>
          <div className="on-hold-fields">
            <div className={`on-hold-field${item.customer_exists ? "" : " on-hold-field--attention"}`}>
              <span className="on-hold-field-label">Customer</span>
              {item.customer_exists ? (
                <strong>{item.customer_name}</strong>
              ) : (
                <Link className="on-hold-customer-link" to={`/rfqs/${item.rfq_id}/customers/new?name=${encodeURIComponent(item.customer_name || "")}`}>
                  {item.customer_name || "Customer name not extracted"}
                </Link>
              )}
              <span className="on-hold-field-note">{item.customer_exists ? "Found in customer records" : "Not found · create customer"}</span>
            </div>
            <div className="on-hold-field">
              <span className="on-hold-field-label">Request</span>
              <strong>{item.rfq_description || "Email RFQ"}</strong>
            </div>
            <div className="on-hold-field">
              <span className="on-hold-field-label">Requested items</span>
              {item.line_items?.length ? (
                <ul>{item.line_items.map((line, index) => (
                  <li key={`${line.product_name || "item"}-${index}`}>
                    {line.product_name || "Item not identified"}{line.quantity != null ? ` · ${line.quantity}` : ""}{line.unit ? ` ${line.unit}` : ""}
                  </li>
                ))}</ul>
              ) : <strong>Items not extracted</strong>}
            </div>
            <div className="on-hold-field">
              <span className="on-hold-field-label">Delivery</span>
              <strong>{item.delivery_location || "Location not provided"}</strong>
              <span className="on-hold-field-note">Required by: {item.required_by_date || "Not provided"}</span>
            </div>
            <div className="on-hold-field">
              <span className="on-hold-field-label">Needs review</span>
              <strong>{item.review_reasons?.length ? item.review_reasons.map((reason) => reason.replaceAll("_", " ")).join(", ") : "Executive review"}</strong>
              {item.sender && <span className="on-hold-field-note">From: {item.sender}</span>}
            </div>
          </div>
          <footer className="on-hold-card-footer">
            <Link to={`/rfqs/${item.rfq_id}/review`}>Review RFQ</Link>
          </footer>
        </article>
      ))}
    </section>
  );
}

export default BidListPage;
