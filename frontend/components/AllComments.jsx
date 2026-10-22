"use client";

/**
 * Community discussion: every comment on every bill, visible to everyone
 * (no sign-in needed to read). Filter by bill. Presentational: the page
 * loads the comments and passes them in.
 */
import { useMemo, useState } from "react";

const PAGE = 10;

export default function AllComments({ comments, loading, error }) {
  const [bill, setBill] = useState("all");
  const [shown, setShown] = useState(PAGE);

  const bills = useMemo(() => {
    const counts = new Map();
    (comments || []).forEach((c) => {
      const k = c.topic_title || "General discussion";
      counts.set(k, (counts.get(k) || 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [comments]);

  const visible = (comments || []).filter(
    (c) => bill === "all" || (c.topic_title || "General discussion") === bill
  );

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <p className="font-mono text-xs text-ink-faint">
          {comments ? `${comments.length} comments across ${bills.length} bills and topics` : ""}
        </p>
        <select
          value={bill}
          onChange={(e) => {
            setBill(e.target.value);
            setShown(PAGE);
          }}
          className="border border-paper-line rounded-sm px-2 py-1.5 text-xs font-mono bg-paper max-w-full"
          aria-label="Filter comments by bill"
        >
          <option value="all">All bills</option>
          {bills.map(([title, n]) => (
            <option key={title} value={title}>
              {title} ({n})
            </option>
          ))}
        </select>
      </div>

      {error && <p className="font-mono text-xs text-seal mb-3">{error}</p>}
      {loading && <p className="font-mono text-xs text-ink-faint">Loading comments…</p>}
      {!loading && !error && visible.length === 0 && (
        <p className="font-mono text-xs text-ink-faint">No comments yet. Open a bill below and be the first.</p>
      )}

      <ul className="space-y-3">
        {visible.slice(0, shown).map((c) => (
          <li key={c.id} className="border border-paper-line rounded-sm px-3 py-2 bg-paper/60">
            <p className="font-mono text-[10px] uppercase tracking-wider text-marigold mb-1 break-words">
              {c.topic_title || "General discussion"}
            </p>
            <p className="text-sm font-body text-ink whitespace-pre-wrap">{c.body}</p>
            <div className="flex items-baseline justify-between gap-2 mt-1.5">
              <span className="font-mono text-[10px] text-ink-faint">{c.author_label}</span>
              <span className="font-mono text-[10px] text-ink-faint">
                {new Date(c.created_at).toLocaleDateString()}
              </span>
            </div>
          </li>
        ))}
      </ul>

      {visible.length > shown && (
        <button
          onClick={() => setShown((n) => n + PAGE)}
          className="mt-4 border border-paper-line rounded-sm px-4 py-1.5 text-xs font-mono uppercase tracking-wide text-ink"
        >
          Show more
        </button>
      )}
    </div>
  );
}
