import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

const API_BASE_URL = "http://127.0.0.1:8000";

function CustomerCreatePage() {
  const { rfqId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [customer, setCustomer] = useState({
    customer_name: searchParams.get("name") || "",
    industry: "",
    country: "",
    segment: "",
    min_margin_pct: "",
    max_discount_pct: "",
  });
  const [policyMode, setPolicyMode] = useState("GLOBAL_DEFAULT");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function updateField(field, value) {
    setCustomer((current) => ({ ...current, [field]: value }));
  }

  async function createCustomer(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/rfqs/customers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...customer,
          min_margin_pct: policyMode === "CUSTOMER_SPECIFIC" ? Number(customer.min_margin_pct) : null,
          max_discount_pct: policyMode === "CUSTOMER_SPECIFIC" ? Number(customer.max_discount_pct) : null,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || "Customer could not be created."));
      }
      navigate(`/rfqs/${rfqId}/review`, { state: { customerId: data.customer_id } });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="content">
      <button type="button" className="back-button" onClick={() => navigate("/bids?tab=on-hold")}>← Back to On Hold</button>
      <div className="page-header">
        <h2>Create customer</h2>
        <span className="hold-badge">For RFQ {rfqId}</span>
      </div>

      <section className="detail-section customer-create-section">
        <p className="muted">Create a customer record, then continue reviewing this RFQ. The active global pricing policy is used by default.</p>
        {error && <div className="message error">{error}</div>}
        <form onSubmit={createCustomer}>
          <div className="review-form-grid">
            <label>Customer name<input autoFocus required value={customer.customer_name} onChange={(event) => updateField("customer_name", event.target.value)} /></label>
            <label>Industry<input value={customer.industry} onChange={(event) => updateField("industry", event.target.value)} /></label>
            <label>Country<input value={customer.country} onChange={(event) => updateField("country", event.target.value)} /></label>
            <label>Segment<input value={customer.segment} onChange={(event) => updateField("segment", event.target.value)} /></label>
          </div>

          <fieldset className="customer-policy-choice">
            <legend>Pricing policy</legend>
            <label><input type="radio" name="customer-policy" checked={policyMode === "GLOBAL_DEFAULT"} onChange={() => setPolicyMode("GLOBAL_DEFAULT")} /> Use active global policy</label>
            <label><input type="radio" name="customer-policy" checked={policyMode === "CUSTOMER_SPECIFIC"} onChange={() => setPolicyMode("CUSTOMER_SPECIFIC")} /> Set customer-specific limits</label>
          </fieldset>

          {policyMode === "CUSTOMER_SPECIFIC" && (
            <div className="review-form-grid custom-policy-fields">
              <label>Minimum margin (%)<input required type="number" min="0" max="100" step="0.01" value={customer.min_margin_pct} onChange={(event) => updateField("min_margin_pct", event.target.value)} /></label>
              <label>Maximum discount (%)<input required type="number" min="0" max="100" step="0.01" value={customer.max_discount_pct} onChange={(event) => updateField("max_discount_pct", event.target.value)} /></label>
            </div>
          )}

          <div className="customer-create-actions">
            <button type="submit" disabled={busy || !customer.customer_name.trim() || (policyMode === "CUSTOMER_SPECIFIC" && (customer.min_margin_pct === "" || customer.max_discount_pct === ""))}>
              {busy ? "Creating…" : "Create customer and continue"}
            </button>
            <button type="button" className="secondary-button" onClick={() => navigate("/bids?tab=on-hold")} disabled={busy}>Cancel</button>
          </div>
        </form>
      </section>
    </main>
  );
}

export default CustomerCreatePage;
