"use client";

/**
 * Every comment on every bill, visible to everyone (no sign-in needed to
 * read), with its sentiment and summary. Filter by bill and by sentiment.
 * Presentational: the page loads the comments and passes them in.
 */
import { useMemo, useState } from "react";
import { SENTIMENTS, SENTIMENT_STYLE } from "../lib/sentiment";
import { CommentItem } from "./CommentSection";

const PAGE = 10;

export default function AllComments({ comments, loading, error }) {
  const [bill, setBill] = useState("all");
  const [mood, setMood] = useState("all");
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
    (c) =>
      (bill === "all" || (c.topic_title || "General discussion") === bill) &&
      (mood === "all" || (mood === "pending" ? !c.sentiment : c.sentiment === mood))
  );

  const selectCls = "border border-paper-line rounded-sm px-2 py-1.5 text-xs font-mono bg-paper max-w-full";

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <p className="font-mono text-xs text-ink-faint">
          {comments ? `${visible.length} of ${comments.length} comments` : ""}
        </p>
        <div className="flex flex-wrap gap-2 max-w-full">
          <select
            value={mood}
            onChange={(e) => {
              setMood(e.target.value);
              setShown(PAGE);
            }}
            className={selectCls}
            aria-label="Filter comments by sentiment"
          >
            <option value="all">All sentiments</option>
            {SENTIMENTS.map((s) => (
              <option key={s} value={s}>
                {SENTIMENT_STYLE[s].label}
              </option>
            ))}
            <option value="pending">Not analysed yet</option>
          </select>
          <select
            value={bill}
            onChange={(e) => {
              setBill(e.target.value);
              setShown(PAGE);
            }}
            className={selectCls}
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
      </div>

      {error && <p className="font-mono text-xs text-seal mb-3">{error}</p>}
      {loading && <p className="font-mono text-xs text-ink-faint">Loading comments…</p>}
      {!loading && !error && visible.length === 0 && (
        <p className="font-mono text-xs text-ink-faint">No comments match. Open a bill below to add one.</p>
      )}

      <ul className="space-y-3">
        {visible.slice(0, shown).map((c) => (
          <CommentItem key={c.id} c={c} showBill />
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
