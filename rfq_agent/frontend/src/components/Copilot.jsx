import { useEffect, useRef, useState } from "react";

const API_BASE_URL = "http://127.0.0.1:8000";

const suggestedQuestions = [
  "Is the current discount within policy?",
  "How does our margin compare with the minimum?",
  "What happens if I quote $100,000?",
];

function Copilot({ bid }) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const conversationEndRef = useRef(null);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(question = message) {
    const trimmedMessage = question.trim();

    if (!trimmedMessage || loading) {
      return;
    }

    setLoading(true);
    setError(null);
    setMessages((previous) => [
      ...previous,
      { role: "user", content: trimmedMessage },
    ]);
    setMessage("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/bids/${bid.bid_id}/copilot`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: trimmedMessage }),
        },
      );

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Copilot request failed.");
      }

      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: data.message },
      ]);
    } catch (err) {
      setMessage(trimmedMessage);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }

  return (
    <section className="detail-section copilot-section" aria-labelledby="copilot-title">
      <div className="copilot-header">
        <div>
          <p className="copilot-eyebrow">OPEN BID · {bid.customer_name}</p>
          <h3 id="copilot-title">Bid Copilot</h3>
          <p className="copilot-description">
            Ask about this quote’s margin, discount, policy limits, or a price scenario.
          </p>
        </div>
        <span className="copilot-bid-label">Bid {bid.bid_id}</span>
      </div>

      <div className="copilot-conversation" aria-live="polite" aria-label="Conversation">
        {messages.length === 0 ? (
          <div className="copilot-empty">
            <strong>What would you like to understand?</strong>
            <p>
              Answers use this bid’s quote data and applicable pricing policy. Risk
              information is kept separate from policy compliance.
            </p>
            <div className="copilot-suggestions" aria-label="Suggested questions">
              {suggestedQuestions.map((question) => (
                <button
                  className="copilot-suggestion"
                  key={question}
                  type="button"
                  onClick={() => handleSend(question)}
                  disabled={loading}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="copilot-messages">
            {messages.map((item, index) => (
              <article
                className={`copilot-message ${item.role}`}
                key={`${item.role}-${index}`}
              >
                <span className="copilot-message-role">
                  {item.role === "user" ? "You" : "Copilot"}
                </span>
                <p>{item.content}</p>
              </article>
            ))}
            {loading && (
              <div className="copilot-typing" role="status">
                <span className="copilot-typing-dot" />
                Checking bid details…
              </div>
            )}
            <div ref={conversationEndRef} />
          </div>
        )}
      </div>

      {error && (
        <div className="message error copilot-error" role="alert">
          {error}
        </div>
      )}

      <form
        className="copilot-composer"
        onSubmit={(event) => {
          event.preventDefault();
          handleSend();
        }}
      >
        <label className="visually-hidden" htmlFor={`copilot-message-${bid.bid_id}`}>
          Ask about this bid
        </label>
        <textarea
          id={`copilot-message-${bid.bid_id}`}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the current margin or discount…"
          rows={2}
          disabled={loading}
        />
        <div className="copilot-composer-footer">
          <span>Enter to send · Shift + Enter for a new line</span>
          <button type="submit" disabled={loading || !message.trim()}>
            {loading ? "Sending…" : "Send"}
          </button>
        </div>
      </form>
    </section>
  );
}

export default Copilot;
