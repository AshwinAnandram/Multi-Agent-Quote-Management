import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const API_BASE_URL = "http://127.0.0.1:8000";

function BidListPage() {
  const navigate = useNavigate();

  const [status, setStatus] = useState("OPEN");
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
    setStatus(newStatus);
    setPage(1);
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
            className={status === "OPEN" ? "active" : ""}
            onClick={() => handleStatusChange("OPEN")}
          >
            Open
          </button>

          <button
            className={status === "CLOSED" ? "active" : ""}
            onClick={() => handleStatusChange("CLOSED")}
          >
            Closed
          </button>

          <button
            className={status === "ALL" ? "active" : ""}
            onClick={() => handleStatusChange("ALL")}
          >
            All
          </button>
        </div>
      </div>

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
    </main>
  );
}

export default BidListPage;