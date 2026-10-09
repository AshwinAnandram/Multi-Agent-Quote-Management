import { useState } from "react";

const API_BASE_URL = "http://127.0.0.1:8000";

function Copilot({ bid }) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSend() {
    const trimmedMessage = message.trim();

    if (!trimmedMessage || loading) {
      return;
    }

    setLoading(true);
    setError(null);

    setMessages((previous) => [
      ...previous,
      {
        role: "user",
        content: trimmedMessage
      }
    ]);

    setMessage("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/bids/${bid.bid_id}/copilot`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            message: trimmedMessage
          })
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Copilot request failed."
        );
      }

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: data.message
        }
      ]);
    } catch (err) {
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
    <div className="copilot">
      <div className="copilot-header">
        <h3>Copilot</h3>
        <span>Bid {bid.bid_id}</span>
      </div>

      <div className="copilot-messages">
        {messages.length === 0 && (
          <div className="copilot-empty">
            <strong>Ask me about this bid</strong>
            <p>
              I can help analyze pricing, risk,
              customer history, and quote strategy.
            </p>
          </div>
        )}

        {messages.map((item, index) => (
          <div
            key={index}
            className={`copilot-message ${item.role}`}
          >
            {item.content}
          </div>
        ))}

        {loading && (
          <div className="copilot-message assistant">
            Thinking...
          </div>
        )}
      </div>

      {error && (
        <div className="message error">
          {error}
        </div>
      )}

      <div className="copilot-input">
        <textarea
          value={message}
          onChange={(event) =>
            setMessage(event.target.value)
          }
          onKeyDown={handleKeyDown}
          placeholder="Ask Copilot..."
          rows={2}
          disabled={loading}
        />

        <button
          onClick={handleSend}
          disabled={loading || !message.trim()}
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}

export default Copilot;