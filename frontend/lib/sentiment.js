/**
 * Shared helpers for the sentiment dashboard (SIH25035):
 * sentiment counts, word-cloud word frequencies and CSV export.
 * The labels themselves come from the backend (Groq, VADER fallback).
 */

export const SENTIMENTS = ["positive", "neutral", "negative"];

export const SENTIMENT_STYLE = {
  positive: { label: "Positive", text: "text-moss", bg: "bg-moss", border: "border-moss" },
  neutral: { label: "Neutral", text: "text-slate", bg: "bg-slate", border: "border-slate" },
  negative: { label: "Negative", text: "text-seal", bg: "bg-seal", border: "border-seal" },
  pending: { label: "Analysing…", text: "text-ink-faint", bg: "bg-paper-line", border: "border-paper-line" },
};

export function countSentiments(comments = []) {
  const counts = { positive: 0, neutral: 0, negative: 0, pending: 0 };
  comments.forEach((c) => {
    if (c.sentiment && counts[c.sentiment] !== undefined) counts[c.sentiment] += 1;
    else counts.pending += 1;
  });
  return counts;
}

// Common English words plus words every comment on a bill uses anyway, so the
// cloud shows what people actually talk about.
const STOPWORDS = new Set(
  `a about above after again against all also am an and any are aren't as at be because been before being below
  between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for
  from further had hadn't has hasn't have haven't having he her here hers herself him himself his how i i'm i've if in
  into is isn't it it's its itself just let's like make made many may me might more most much must mustn't my myself
  need no nor not now of off on once only or other ought our ours ourselves out over own per same shall shan't she
  should shouldn't so some such than that that's the their theirs them themselves then there there's these they
  they're this those through to too under until up upon us very was wasn't we we're were weren't what what's when
  where which while who whom why will with won't would wouldn't you you're your yours yourself yourselves also
  get got one two even well really think thing things way going want etc yes ok okay bill bills act law laws
  government govt section sections clause clauses amendment amendments proposed provision provisions new india
  indian people would also hai ka ki ke ko se mein aur nahi bhi yeh ye`
    .split(/\s+/)
    .filter(Boolean)
);

/** Returns [[word, count], ...] sorted by count, for the word cloud. */
export function wordFrequencies(comments = [], max = 60) {
  const freq = new Map();
  comments.forEach((c) => {
    const words = (c.body || "")
      .toLowerCase()
      .replace(/https?:\/\/\S+/g, " ")
      .match(/[\p{L}][\p{L}'-]*/gu);
    (words || []).forEach((raw) => {
      const w = raw.replace(/^'+|'+$/g, "").replace(/'s$/, "");
      if (w.length < 3 || STOPWORDS.has(w)) return;
      freq.set(w, (freq.get(w) || 0) + 1);
    });
  });
  return [...freq.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, max);
}

/** Most common sentiment among comments that use `word` — colours the word cloud. */
export function wordSentiment(comments, word) {
  const counts = { positive: 0, neutral: 0, negative: 0 };
  const re = new RegExp(`(^|[^\\p{L}])${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "iu");
  comments.forEach((c) => {
    if (c.sentiment && counts[c.sentiment] !== undefined && re.test(c.body || "")) counts[c.sentiment] += 1;
  });
  const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  return best && best[1] > 0 ? best[0] : null;
}

/** Download the comments with their analysis as a CSV file (for officials). */
export function downloadCsv(comments, filename = "janmat-comments.csv") {
  const cols = ["id", "bill", "created_at", "author", "sentiment", "confidence", "summary", "comment"];
  const esc = (v) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = comments.map((c) =>
    [
      c.id,
      c.topic_title || "General discussion",
      c.created_at,
      c.author_label,
      c.sentiment || "",
      c.sentiment_score ?? "",
      c.summary || "",
      c.body,
    ]
      .map(esc)
      .join(",")
  );
  const blob = new Blob(["﻿" + [cols.join(","), ...rows].join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
