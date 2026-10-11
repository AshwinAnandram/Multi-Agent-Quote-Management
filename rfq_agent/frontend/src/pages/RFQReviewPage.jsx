import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

const API_BASE_URL = "http://127.0.0.1:8000";

function RFQReviewPage() {
  const { rfqId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const createdCustomerId = location.state?.customerId;
  const [rfq, setRfq] = useState(null);
  const [options, setOptions] = useState({ customers: [], products: [], sales_reps: [] });
  const [form, setForm] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showCreateCustomer, setShowCreateCustomer] = useState(false);
  const [newCustomer, setNewCustomer] = useState({ customer_name: "", industry: "", country: "", segment: "", min_margin_pct: "", max_discount_pct: "" });
  const [newCustomerPolicyMode, setNewCustomerPolicyMode] = useState("GLOBAL_DEFAULT");
  const [confirmConflicts, setConfirmConflicts] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE_URL}/rfqs/${rfqId}/review`).then(readResponse),
      fetch(`${API_BASE_URL}/rfqs/review-options`).then(readResponse),
    ]).then(([review, reviewOptions]) => {
      setRfq(review);
      setOptions(reviewOptions);
      const saved = review.extracted_json?.review_values || {};
      const extracted = review.extracted_json?.intake?.merged || {};
      const extractedRFQ = extracted.rfq || {};
      setForm({
        customer_id: createdCustomerId || review.customer_id || "",
        sales_rep_id: saved.sales_rep_id || "",
        rfq_description: saved.rfq_description ?? review.rfq_description ?? extractedRFQ.subject ?? "",
        required_by_date: saved.required_by_date ?? review.required_by_date ?? extractedRFQ.required_by_date ?? "",
        delivery_location: saved.delivery_location ?? review.delivery_location ?? extractedRFQ.delivery_location ?? "",
        currency: saved.currency ?? review.currency ?? extractedRFQ.currency ?? "",
        payment_terms: saved.payment_terms ?? review.payment_terms ?? extractedRFQ.payment_terms ?? "",
        opening_quote_price: saved.opening_quote_price ?? "",
        deal_size: saved.deal_size ?? extractedRFQ.deal_size ?? "",
        line_items: review.line_items.map((item) => ({
          ...item,
          line_item_id: item.rfq_line_item_id,
          product_id: item.product_id || "",
          quantity: item.quantity ?? "",
          product_name_raw: item.product_name_raw ?? "",
          unit: item.unit ?? "",
          requirements: item.requirements ?? "",
        })),
      });
    }).catch((err) => setError(err.message));
  }, [rfqId, createdCustomerId]);

  const email = rfq?.extracted_json || {};
  const intake = email.intake || {};
  const quoteFallback = form?.opening_quote_price || "";

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateLine(index, field, value) {
    setForm((current) => ({
      ...current,
      line_items: current.line_items.map((line, lineIndex) =>
        lineIndex === index ? { ...line, [field]: value } : line
      ),
    }));
  }

  function addLineItem() {
    setForm((current) => ({
      ...current,
      line_items: [...current.line_items, {
        rfq_line_item_id: null,
        line_item_id: null,
        product_name_raw: "",
        product_id: "",
        quantity: "",
        unit: "",
        requirements: "",
      }],
    }));
  }

  async function saveReview() {
    setBusy(true); setError(""); setMessage("");
    try {
      const payload = {
        ...form,
        customer_id: form.customer_id ? Number(form.customer_id) : null,
        sales_rep_id: form.sales_rep_id ? Number(form.sales_rep_id) : null,
        opening_quote_price: form.opening_quote_price ? Number(form.opening_quote_price) : null,
        deal_size: form.deal_size ? Number(form.deal_size) : (form.opening_quote_price ? Number(form.opening_quote_price) : null),
        line_items: form.line_items.map((line) => ({
          ...line,
          line_item_id: line.rfq_line_item_id ? Number(line.rfq_line_item_id) : null,
          product_id: line.product_id ? Number(line.product_id) : null,
          quantity: line.quantity === "" ? null : Number(line.quantity),
        })),
      };
      delete payload.rfq_id;
      await readResponse(await fetch(`${API_BASE_URL}/rfqs/${rfqId}/review`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      }));
      const refreshed = await readResponse(await fetch(`${API_BASE_URL}/rfqs/${rfqId}/review`));
      setRfq(refreshed);
      setForm((current) => ({
        ...current,
        line_items: refreshed.line_items.map((line) => ({
          ...line,
          line_item_id: line.rfq_line_item_id,
          product_id: line.product_id || "",
          quantity: line.quantity ?? "",
          product_name_raw: line.product_name_raw ?? "",
          unit: line.unit ?? "",
          requirements: line.requirements ?? "",
        })),
      }));
      setMessage("Review saved.");
      return true;
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
    return false;
  }

  async function rejectRFQ() {
    const reason = window.prompt("Reason for rejecting this request:");
    if (!reason) return;
    setBusy(true); setError("");
    try {
      await readResponse(await fetch(`${API_BASE_URL}/rfqs/${rfqId}/reject`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }),
      }));
      navigate("/bids");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function addCustomer() {
    setBusy(true); setError("");
    try {
      const customer = await readResponse(await fetch(`${API_BASE_URL}/rfqs/customers`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...newCustomer,
          min_margin_pct: newCustomerPolicyMode === "CUSTOMER_SPECIFIC" && newCustomer.min_margin_pct !== "" ? Number(newCustomer.min_margin_pct) : null,
          max_discount_pct: newCustomerPolicyMode === "CUSTOMER_SPECIFIC" && newCustomer.max_discount_pct !== "" ? Number(newCustomer.max_discount_pct) : null,
        }),
      }));
      setOptions((current) => ({
        ...current,
        customers: [...current.customers.filter((item) => item.customer_id !== customer.customer_id), customer]
          .sort((left, right) => left.customer_name.localeCompare(right.customer_name)),
      }));
      updateField("customer_id", customer.customer_id);
      setShowCreateCustomer(false);
      setNewCustomer({ customer_name: "", industry: "", country: "", segment: "", min_margin_pct: "", max_discount_pct: "" });
      setNewCustomerPolicyMode("GLOBAL_DEFAULT");
      setMessage(customer.created
        ? customer.policy_mode === "CUSTOMER_SPECIFIC"
          ? "Customer and active customer-specific pricing policy created and selected."
          : "Customer created and selected. It will use the active global policy."
        : "An existing customer with this name was selected. Its pricing policy was left unchanged.");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function acceptRequest() {
    if (!(await saveReview())) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await readResponse(await fetch(`${API_BASE_URL}/rfqs/${rfqId}/accept`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm_source_conflicts: confirmConflicts }),
      }));
      navigate(`/bids/${result.bid_id}`);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  const conflictCount = useMemo(() => intake.conflicts?.length || 0, [intake]);

  if (error && !rfq) return <main className="content"><div className="message error">{error}</div></main>;
  if (!rfq || !form) return <main className="content"><div className="message">Loading RFQ review...</div></main>;

  return (
    <main className="content">
      <button className="back-button" onClick={() => navigate("/bids?tab=on-hold")}>← Back to On Hold</button>
      <div className="page-header"><h2>Review RFQ {rfq.rfq_id}</h2><span className="hold-badge">On Hold</span></div>

      {error && <div className="message error">{error}</div>}
      {message && <div className="message success">{message}</div>}

      <section className="detail-section">
        <h3>Original email</h3>
        <div className="email-meta"><strong>From:</strong> {email.sender || "Unknown"}</div>
        <div className="email-meta"><strong>Subject:</strong> {email.subject || "(no subject)"}</div>
        <div className="email-meta"><strong>Received:</strong> {email.received_at || "Unknown"}</div>
        <pre className="email-body">{email.body || "No email body was captured."}</pre>
      </section>

      <section className="detail-section">
        <h3>Extracted fields</h3>
        {conflictCount > 0 && <div className="review-alert">{conflictCount} conflict(s) between the email and its attachments require your review.</div>}
        {(intake.issues || []).map((issue, index) => <div className="review-alert" key={`${issue.code}-${index}`}>{issue.source}: {issue.message}</div>)}
        {(intake.missing_fields || []).length > 0 && <p className="muted">Initially missing from source: {intake.missing_fields.join(", ")}</p>}
        {(intake.conflicts || []).map((conflict, index) => (
          <div className="conflict-card" key={`${conflict.field}-${index}`}>
            <strong>{conflict.field}</strong>
            <span>{conflict.source_a}: {formatValue(conflict.value_a)}</span>
            <span>{conflict.source_b}: {formatValue(conflict.value_b)}</span>
          </div>
        ))}
        <details className="attachment-detail">
          <summary>Consolidated extracted values</summary>
          <pre>{JSON.stringify(intake.merged || {}, null, 2)}</pre>
        </details>
        {(email.attachments || []).map((attachment) => (
          <details className="attachment-detail" key={attachment.filename}>
            <summary>{attachment.filename} · {attachment.status}</summary>
            {attachment.error && <p>{attachment.error}</p>}
            {attachment.extracted_text && <pre>{attachment.extracted_text}</pre>}
          </details>
        ))}
        <p className="muted">Review the extracted data and resolve conflicts before accepting.</p>
      </section>

      <section className="detail-section">
        <h3>Bid details</h3>
        {showCreateCustomer && <div className="new-customer-form">
          <h4>Create customer record</h4>
          <p className="muted">Choose the active global policy or set customer-specific limits. Customer-specific limits apply to new records created here.</p>
          <div className="review-form-grid">
            <label>Customer name<input value={newCustomer.customer_name} onChange={(e) => setNewCustomer((value) => ({ ...value, customer_name: e.target.value }))} /></label>
            <label>Industry<input value={newCustomer.industry} onChange={(e) => setNewCustomer((value) => ({ ...value, industry: e.target.value }))} /></label>
            <label>Country<input value={newCustomer.country} onChange={(e) => setNewCustomer((value) => ({ ...value, country: e.target.value }))} /></label>
            <label>Segment<input value={newCustomer.segment} onChange={(e) => setNewCustomer((value) => ({ ...value, segment: e.target.value }))} /></label>
          </div>
          <div className="policy-choice">
            <label><input type="radio" name="new-customer-policy" checked={newCustomerPolicyMode === "GLOBAL_DEFAULT"} onChange={() => setNewCustomerPolicyMode("GLOBAL_DEFAULT")} /> Use active global policy</label>
            <label><input type="radio" name="new-customer-policy" checked={newCustomerPolicyMode === "CUSTOMER_SPECIFIC"} onChange={() => setNewCustomerPolicyMode("CUSTOMER_SPECIFIC")} /> Set customer-specific limits</label>
          </div>
          {newCustomerPolicyMode === "CUSTOMER_SPECIFIC" && <div className="review-form-grid custom-policy-fields">
            <label>Minimum margin (%)<input type="number" min="0" max="100" step="0.01" value={newCustomer.min_margin_pct} onChange={(e) => setNewCustomer((value) => ({ ...value, min_margin_pct: e.target.value }))} /></label>
            <label>Maximum discount (%)<input type="number" min="0" max="100" step="0.01" value={newCustomer.max_discount_pct} onChange={(e) => setNewCustomer((value) => ({ ...value, max_discount_pct: e.target.value }))} /></label>
            <p className="muted">Enter both limits to create a customer-specific policy.</p>
          </div>}
          <div className="customer-actions"><button type="button" onClick={addCustomer} disabled={busy || !newCustomer.customer_name.trim() || (newCustomerPolicyMode === "CUSTOMER_SPECIFIC" && (!newCustomer.min_margin_pct || !newCustomer.max_discount_pct))}>Create and select</button><button type="button" onClick={() => setShowCreateCustomer(false)}>Cancel</button></div>
        </div>}
        <div className="review-form-grid">
          <label>Customer<select value={form.customer_id} onChange={(e) => updateField("customer_id", e.target.value)}><option value="">Select customer…</option>{options.customers.map((item) => <option key={item.customer_id} value={item.customer_id}>{item.customer_name}</option>)}</select><button type="button" className="small-action" onClick={() => setShowCreateCustomer((value) => !value)}>Create new customer</button></label>
          <label>Sales executive<select value={form.sales_rep_id} onChange={(e) => updateField("sales_rep_id", e.target.value)}><option value="">Select executive…</option>{options.sales_reps.map((item) => <option key={item.sales_rep_id} value={item.sales_rep_id}>{item.sales_rep_name}{item.region ? ` · ${item.region}` : ""}</option>)}</select></label>
          <label>Request title<input value={form.rfq_description} onChange={(e) => updateField("rfq_description", e.target.value)} /></label>
          <label>Required by<input type="date" value={String(form.required_by_date).slice(0, 10)} onChange={(e) => updateField("required_by_date", e.target.value)} /></label>
          <label>Delivery location<input value={form.delivery_location} onChange={(e) => updateField("delivery_location", e.target.value)} /></label>
          <label>Currency<input value={form.currency} onChange={(e) => updateField("currency", e.target.value)} /></label>
          <label>Payment terms<input value={form.payment_terms} onChange={(e) => updateField("payment_terms", e.target.value)} /></label>
          <label>Opening quote price<input type="number" min="0.01" step="0.01" value={form.opening_quote_price} onChange={(e) => updateField("opening_quote_price", e.target.value)} /></label>
          <label>Deal size<input type="number" min="0.01" step="0.01" placeholder={quoteFallback || "Defaults to opening quote"} value={form.deal_size} onChange={(e) => updateField("deal_size", e.target.value)} /></label>
        </div>
        <h4>Requested items</h4>
        <button type="button" className="small-action add-line-button" onClick={addLineItem}>Add requested item</button>
        {form.line_items.map((line, index) => (
          <div className="rfq-line-editor" key={line.rfq_line_item_id || `new-${index}`}>
            <label>Customer item<input value={line.product_name_raw} onChange={(e) => updateLine(index, "product_name_raw", e.target.value)} /></label>
            <label>Catalog product<select value={line.product_id} onChange={(e) => updateLine(index, "product_id", e.target.value)}><option value="">Map product…</option>{options.products.map((product) => <option key={product.product_id} value={product.product_id}>{product.product_name}</option>)}</select></label>
            <label>Quantity<input type="number" min="0.01" step="any" value={line.quantity} onChange={(e) => updateLine(index, "quantity", e.target.value)} /></label>
            <label>Unit<input value={line.unit} onChange={(e) => updateLine(index, "unit", e.target.value)} /></label>
            <label>Requirements<input value={line.requirements} onChange={(e) => updateLine(index, "requirements", e.target.value)} /></label>
          </div>
        ))}
      </section>

      <div className="review-actions">
        <button onClick={saveReview} disabled={busy}>{busy ? "Saving…" : "Save review"}</button>
        {conflictCount > 0 && <label className="conflict-confirm"><input type="checkbox" checked={confirmConflicts} onChange={(e) => setConfirmConflicts(e.target.checked)} /> I reviewed the source conflicts and selected the values to use.</label>}
        <button className="accept-button" onClick={acceptRequest} disabled={busy || (conflictCount > 0 && !confirmConflicts)}>{busy ? "Processing…" : "Accept and create open bid"}</button>
        <button className="reject-button" onClick={rejectRFQ} disabled={busy}>Reject request</button>
        <span className="muted">Acceptance creates an open bid only when it passes the active pricing policy.</span>
      </div>
    </main>
  );
}

async function readResponse(response) {
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || "Request failed."));
  return data;
}

function formatValue(value) {
  return value === null || value === undefined || value === "" ? "(empty)" : JSON.stringify(value);
}

export default RFQReviewPage;
