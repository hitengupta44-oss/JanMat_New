"use client";

/**
 * Word cloud of the words commenters use most. Bigger = used more often;
 * colour = the sentiment of most comments that use the word.
 * Pure HTML/CSS (no canvas library), so it's light and readable on phones.
 */
import { useMemo } from "react";
import { SENTIMENT_STYLE, wordFrequencies, wordSentiment } from "../lib/sentiment";

export default function WordCloud({ comments = [], max = 50 }) {
  const words = useMemo(() => {
    const freq = wordFrequencies(comments, max);
    if (!freq.length) return [];
    const top = freq[0][1];
    const low = freq[freq.length - 1][1];
    const scaled = freq.map(([word, count]) => {
      const t = top === low ? 1 : (count - low) / (top - low);
      return { word, count, size: 0.8 + t * 1.6, sentiment: wordSentiment(comments, word) };
    });
    // Interleave big and small words so the cloud doesn't read as a sorted list.
    const out = [];
    let i = 0;
    let j = scaled.length - 1;
    while (i <= j) {
      out.push(scaled[i++]);
      if (i <= j) out.push(scaled[j--]);
    }
    return out;
  }, [comments, max]);

  if (!words.length) {
    return <p className="font-mono text-xs text-ink-faint">Not enough comment text for a word cloud yet.</p>;
  }

  return (
    <div
      className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border border-paper-line rounded-sm bg-paper/60 px-4 py-5"
      aria-label="Word cloud of the most common words in comments"
    >
      {words.map((w) => (
        <span
          key={w.word}
          title={`"${w.word}" used ${w.count} time${w.count === 1 ? "" : "s"}`}
          className={`font-display leading-tight ${w.sentiment ? SENTIMENT_STYLE[w.sentiment].text : "text-ink"}`}
          style={{ fontSize: `${w.size}rem`, fontWeight: w.size > 1.6 ? 600 : 400 }}
        >
          {w.word}
        </span>
      ))}
    </div>
  );
}
