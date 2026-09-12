"use client";

/**
 * JanMat chat widget — talks directly to the Gradio Space's auto-generated
 * API using only fetch(), no extra npm dependency needed.
 *
 * Usage: <JanMatChatWidget spaceUrl="https://beastzzz-janmat.hf.space" />
 */
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
  let errorMessage = null;

  // Gradio's SSE stream sends several event types: "generating" (partial
  // results), "complete" (the final payload), "error", and periodic
  // heartbeats that carry null. We track the last NON-NULL data payload
  // rather than simply the last line, because the stream frequently ends
  // with a heartbeat or completion marker that has no payload of its own —
  // which previously left us with nothing and threw "No data received".
  const handleLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;

    if (trimmed.startsWith("event:")) {
      if (trimmed.slice(6).trim() === "error") errorMessage = "Gradio reported an error event";
      return;
    }
    if (!trimmed.startsWith("data:")) return;

    const raw = trimmed.slice(5).trim();
    if (!raw || raw === "null") return;

    try {
      const parsed = JSON.parse(raw);
      if (parsed !== null && parsed !== undefined) lastData = parsed;
    } catch {
      // A data line split across chunk boundaries — it'll be completed and
      // re-handled once the rest of it arrives.
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Only process COMPLETE lines; keep any trailing partial line in the
    // buffer for the next chunk. (The previous version re-split the entire
    // buffer each time, re-parsing lines it had already handled.)
    let newlineIndex;
    while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
      handleLine(buffer.slice(0, newlineIndex));
      buffer = buffer.slice(newlineIndex + 1);
    }
  }

  // Flush whatever remains after the stream closes without a final newline.
  handleLine(buffer);

  if (lastData === null) {
    throw new Error(errorMessage || "No data received from Gradio Space");
  }
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

      if (newSessionId) setSessionId(newSessionId);

      // app.py's chat_fn returns history as [[user, bot], ...]. Pull the bot
      // side of the last turn, and guard every step — an empty history or a
      // null bot reply previously rendered as a blank chat bubble with no
      // indication anything had gone wrong.
      let botReply = "";
      if (Array.isArray(updatedHistory) && updatedHistory.length > 0) {
        const lastTurn = updatedHistory[updatedHistory.length - 1];
        if (Array.isArray(lastTurn)) {
          botReply = lastTurn[1] ?? "";
        } else if (typeof lastTurn === "string") {
          botReply = lastTurn;
        }
      }

      if (!botReply || !String(botReply).trim()) {
        botReply =
          "I didn't get a usable answer back for that one. Try rephrasing, or ask about a specific bill by name.";
      }

      setMessages((m) => [...m, { role: "assistant", content: String(botReply) }]);
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
            {m.role === "user" ? (
              <span className="inline-block rounded-sm px-3 py-2 max-w-[85%] text-sm whitespace-pre-wrap font-body bg-ink text-paper">
                {m.content}
              </span>
            ) : (
              // Answers come back as markdown (headings, bold, tables, lists).
              // Rendering it rather than printing raw ** and ### keeps long
              // legislative answers readable. Each element is styled to match
              // the site's paper/ink type rather than browser defaults.
              <div className="inline-block rounded-sm px-4 py-3 max-w-[92%] text-left bg-paper border border-paper-line text-ink">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h1: ({ children }) => (
                      <h4 className="font-display text-base text-ink mt-3 mb-1.5 first:mt-0">{children}</h4>
                    ),
                    h2: ({ children }) => (
                      <h4 className="font-display text-base text-ink mt-3 mb-1.5 first:mt-0">{children}</h4>
                    ),
                    h3: ({ children }) => (
                      <h5 className="font-display text-sm text-ink mt-3 mb-1 first:mt-0">{children}</h5>
                    ),
                    p: ({ children }) => (
                      <p className="font-body text-sm leading-relaxed text-ink mb-2 last:mb-0">{children}</p>
                    ),
                    ul: ({ children }) => (
                      <ul className="list-disc pl-5 mb-2 space-y-1 font-body text-sm text-ink">{children}</ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="list-decimal pl-5 mb-2 space-y-1 font-body text-sm text-ink">{children}</ol>
                    ),
                    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                    strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
                    em: ({ children }) => <em className="italic">{children}</em>,
                    a: ({ href, children }) => (
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer"
                        className="underline decoration-paper-line hover:decoration-ink break-words"
                      >
                        {children}
                      </a>
                    ),
                    code: ({ inline, children }) =>
                      inline ? (
                        <code className="font-mono text-[0.8em] bg-paper-line/40 px-1 py-0.5 rounded-sm">
                          {children}
                        </code>
                      ) : (
                        <code className="block font-mono text-xs bg-paper-line/30 p-2 rounded-sm overflow-x-auto my-2">
                          {children}
                        </code>
                      ),
                    hr: () => <hr className="border-paper-line my-3" />,
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-2 border-paper-line pl-3 italic text-ink-faint my-2">
                        {children}
                      </blockquote>
                    ),
                    // Tables are common in these answers (provision/effect
                    // comparisons) and need horizontal scroll on mobile.
                    table: ({ children }) => (
                      <div className="overflow-x-auto my-3">
                        <table className="w-full text-left border-collapse text-xs font-body">{children}</table>
                      </div>
                    ),
                    thead: ({ children }) => <thead className="border-b border-paper-line">{children}</thead>,
                    th: ({ children }) => (
                      <th className="py-1.5 pr-3 font-mono text-[10px] uppercase tracking-wide text-ink-faint align-top">
                        {children}
                      </th>
                    ),
                    td: ({ children }) => (
                      <td className="py-1.5 pr-3 align-top border-b border-paper-line/50 leading-relaxed">
                        {children}
                      </td>
                    ),
                  }}
                >
                  {m.content}
                </ReactMarkdown>
              </div>
            )}
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
