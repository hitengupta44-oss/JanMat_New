"use client";

import { SENTIMENTS, SENTIMENT_STYLE, countSentiments } from "../lib/sentiment";

/** Small label showing one comment's sentiment. */
export function SentimentBadge({ sentiment, score }) {
  const s = SENTIMENT_STYLE[sentiment] || SENTIMENT_STYLE.pending;
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider border rounded-sm px-1.5 py-0.5 ${s.text} ${s.border}`}
      title={score != null ? `Confidence ${Math.round(score * 100)}%` : undefined}
    >
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${s.bg}`} aria-hidden />
      {s.label}
    </span>
  );
}

/** Stacked bar + legend showing how comments split by sentiment. */
export function SentimentBar({ comments }) {
  const counts = countSentiments(comments);
  const analysed = counts.positive + counts.neutral + counts.negative;
  if (!comments.length) return <p className="font-mono text-xs text-ink-faint">No comments yet.</p>;

  return (
    <div>
      <div
        className="flex h-3 w-full rounded-sm overflow-hidden bg-paper-line"
        role="img"
        aria-label={`Positive ${counts.positive}, neutral ${counts.neutral}, negative ${counts.negative}`}
      >
        {SENTIMENTS.map((s) =>
          counts[s] ? (
            <div
              key={s}
              className={`${SENTIMENT_STYLE[s].bg} h-full border-r-2 border-paper last:border-r-0`}
              style={{ width: `${(counts[s] / Math.max(analysed, 1)) * 100}%` }}
            />
          ) : null
        )}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2">
        {SENTIMENTS.map((s) => (
          <span key={s} className="font-mono text-xs text-ink">
            <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${SENTIMENT_STYLE[s].bg}`} aria-hidden />
            {SENTIMENT_STYLE[s].label} <strong>{counts[s]}</strong>
            <span className="text-ink-faint">
              {" "}
              ({analysed ? Math.round((counts[s] / analysed) * 100) : 0}%)
            </span>
          </span>
        ))}
        {counts.pending > 0 && (
          <span className="font-mono text-xs text-ink-faint">{counts.pending} awaiting analysis</span>
        )}
      </div>
    </div>
  );
}

/** Overall summary + key points produced by the backend for a bill (or all bills). */
export function InsightSummary({ insight }) {
  if (!insight || !insight.overall_summary) {
    return (
      <p className="font-mono text-xs text-ink-faint">
        Summary will appear once comments have been analysed.
      </p>
    );
  }
  const points = Array.isArray(insight.key_points) ? insight.key_points : [];
  return (
    <div>
      <p className="font-body text-sm text-ink leading-relaxed">{insight.overall_summary}</p>
      {points.length > 0 && (
        <ul className="list-disc pl-5 mt-2 space-y-1 font-body text-sm text-ink">
          {points.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      )}
      {insight.updated_at && (
        <p className="font-mono text-[10px] text-ink-faint mt-2">
          Based on {insight.comment_count} comment{insight.comment_count === 1 ? "" : "s"} · updated{" "}
          {new Date(insight.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}
