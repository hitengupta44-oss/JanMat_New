"use client";

/**
 * Sentiment dashboard (SIH 2025, PS SIH25035): how public comments on every
 * PRS-tracked bill break down by sentiment, an overall summary, a word cloud,
 * and a per-bill breakdown. Readable by everyone; data comes from the
 * public_comments and public_topic_insights views.
 */
import { useMemo, useState } from "react";
import { SENTIMENTS, SENTIMENT_STYLE, SOURCES, bySource, countSentiments, downloadCsv } from "../lib/sentiment";
import { InsightSummary, SentimentBar } from "./SentimentParts";
import WordCloud from "./WordCloud";

export const ALL_TOPICS_KEY = "janmat:all";

function Stat({ label, value, tone = "text-ink" }) {
  return (
    <div className="border border-paper-line rounded-sm px-3 py-2 bg-paper/60">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">{label}</p>
      <p className={`font-display text-2xl ${tone}`}>{value}</p>
    </div>
  );
}

function MiniBar({ counts }) {
  const total = counts.positive + counts.neutral + counts.negative;
  if (!total) return <span className="font-mono text-[10px] text-ink-faint">pending</span>;
  return (
    <div className="flex h-2 w-full min-w-[80px] rounded-sm overflow-hidden bg-paper-line">
      {SENTIMENTS.map((s) =>
        counts[s] ? (
          <div key={s} className={SENTIMENT_STYLE[s].bg} style={{ width: `${(counts[s] / total) * 100}%` }} />
        ) : null
      )}
    </div>
  );
}

export default function InsightsDashboard({ comments, insights, loading }) {
  const [bill, setBill] = useState("all");
  const [who, setWho] = useState("all");
  const all = useMemo(() => bySource(comments || [], who), [comments, who]);
  const prsCount = (comments || []).filter((c) => c.source === "prs").length;

  const byBill = useMemo(() => {
    const m = new Map();
    all.forEach((c) => {
      const key = c.topic_key;
      if (!m.has(key)) m.set(key, { key, title: c.topic_title || "General discussion", items: [] });
      m.get(key).items.push(c);
    });
    return [...m.values()]
      .map((b) => ({ ...b, counts: countSentiments(b.items) }))
      .sort((a, b) => b.items.length - a.items.length);
  }, [all]);

  const selected = bill === "all" ? null : byBill.find((b) => b.key === bill);
  const scoped = selected ? selected.items : all;
  const counts = countSentiments(scoped);
  const analysed = counts.positive + counts.neutral + counts.negative;
  const pct = (n) => (analysed ? `${Math.round((n / analysed) * 100)}%` : "–");
  const insight = (insights || {})[selected ? selected.key : ALL_TOPICS_KEY];

  if (loading) return <p className="font-mono text-xs text-ink-faint">Loading dashboard…</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <select
          value={bill}
          onChange={(e) => setBill(e.target.value)}
          className="border border-paper-line rounded-sm px-2 py-1.5 text-xs font-mono bg-paper max-w-full"
          aria-label="Choose which bill the dashboard shows"
        >
          <option value="all">All bills ({all.length} comments)</option>
          {byBill.map((b) => (
            <option key={b.key} value={b.key}>
              {b.title} ({b.items.length})
            </option>
          ))}
        </select>
        <select
          value={who}
          onChange={(e) => {
            setWho(e.target.value);
            setBill("all");
          }}
          className="border border-paper-line rounded-sm px-2 py-1.5 text-xs font-mono bg-paper max-w-full"
          aria-label="Choose whose comments the dashboard shows"
        >
          {SOURCES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <button
          onClick={() => downloadCsv(scoped, selected ? "janmat-bill-comments.csv" : "janmat-all-comments.csv")}
          disabled={!scoped.length}
          className="border border-ink rounded-sm px-3 py-1.5 text-xs font-mono uppercase tracking-wide text-ink disabled:opacity-40"
        >
          Download CSV
        </button>
      </div>

      {prsCount > 0 && who !== "janmat" && (
        <p className="font-mono text-[10px] text-ink-faint leading-relaxed">
          Includes {prsCount} stakeholder view{prsCount === 1 ? "" : "s"} extracted from PRS Legislative Research
          analysis and committee reports, marked &quot;From PRS&quot;.
        </p>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Comments" value={scoped.length} />
        <Stat label="Positive" value={pct(counts.positive)} tone="text-moss" />
        <Stat label="Neutral" value={pct(counts.neutral)} tone="text-slate" />
        <Stat label="Negative" value={pct(counts.negative)} tone="text-seal" />
      </div>

      <div>
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-faint mb-2">Sentiment split</p>
        <SentimentBar comments={scoped} />
      </div>

      <div>
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-faint mb-2">
          {selected ? "Summary of comments on this bill" : "Overall summary"}
        </p>
        <InsightSummary insight={insight} />
      </div>

      <div>
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-faint mb-2">Word cloud</p>
        <WordCloud comments={scoped} />
        <p className="font-mono text-[10px] text-ink-faint mt-1.5">
          Bigger words are used more often. Colour shows the sentiment of most comments using that word.
        </p>
      </div>

      {!selected && byBill.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-faint mb-2">By bill</p>
          <ul className="divide-y divide-paper-line border-y border-paper-line">
            {byBill.map((b) => (
              <li key={b.key}>
                <button
                  onClick={() => setBill(b.key)}
                  className="w-full grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_140px_70px] items-center gap-x-4 gap-y-1 py-2.5 text-left group"
                >
                  <span className="font-body text-sm text-ink group-hover:text-marigold break-words">{b.title}</span>
                  <span className="font-mono text-xs text-ink-faint text-right sm:order-last">{b.items.length}</span>
                  <span className="col-span-2 sm:col-span-1">
                    <MiniBar counts={b.counts} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
