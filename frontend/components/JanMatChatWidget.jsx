"use client";

/**
 * JanMat chat widget — talks directly to the Gradio Space's auto-generated
 * API using only fetch(), no extra npm dependency needed.
 *
 * Usage: <JanMatChatWidget spaceUrl="https://beastzzz-janmat.hf.space" />
 */
import { useState } from "react";

async function callGradioApi(spaceUrl, apiName, payload) {
  const base = spaceUrl.replace(/\/$/, "");

  const startRes = await fetch(`${base}/call/${apiName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data: payload }),
  });
  if (!startRes.ok) throw new Error(`Gradio call failed to start: ${startRes.status}`);
  const { event_id } = await startRes.json();

  const streamRes = await fetch(`${base}/call/${apiName}/${event_id}`);
  if (!streamRes.ok || !streamRes.body) throw new Error(`Gradio stream failed: ${streamRes.status}`);

  const reader = streamRes.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastData = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          lastData = JSON.parse(line.slice(6));
        } catch {
          // ignore partial/incomplete lines, keep buffering
        }
      }
    }
  }

  if (!lastData) throw new Error("No data received from Gradio Space");
  return lastData;
}

export default function JanMatChatWidget({ spaceUrl }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);

  async function sendMessage() {
    const text = input.trim();
    if (!text) return;

    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const result = await callGradioApi(spaceUrl, "chat", [text, [], sessionId]);
      const [updatedHistory, , newSessionId] = result;

      setSessionId(newSessionId);

      const lastTurn = updatedHistory[updatedHistory.length - 1];
      const botReply = Array.isArray(lastTurn) ? lastTurn[1] : String(lastTurn);

      setMessages((m) => [...m, { role: "assistant", content: botReply }]);
    } catch (err) {
      console.error("JanMat chat error:", err);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "Sorry, I couldn't reach the chatbot right now. Please try again shortly." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col border border-paper-line rounded-sm w-full max-w-xl h-[520px] bg-paper/60">
      <div className="px-4 py-3 border-b border-paper-line">
        <h3 className="font-display text-lg text-ink">Ask JanMat</h3>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="font-mono text-xs text-ink-faint">
            Ask about any ingested bill, e.g. &quot;What does the Data Protection Bill say about consent?&quot;
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <span
              className={
                "inline-block rounded-sm px-3 py-2 max-w-[85%] text-sm whitespace-pre-wrap font-body " +
                (m.role === "user" ? "bg-ink text-paper" : "bg-paper border border-paper-line text-ink")
              }
            >
              {m.content}
            </span>
          </div>
        ))}
        {loading && <p className="font-mono text-xs text-ink-faint">Thinking…</p>}
      </div>

      <div className="flex items-center gap-2 p-3 border-t border-paper-line">
        <input
          className="flex-1 border border-paper-line rounded-sm px-3 py-2 text-sm font-body bg-paper"
          placeholder="Type your question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading}
          className="bg-ink text-paper rounded-sm px-4 py-2 text-sm font-mono uppercase tracking-wide disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
