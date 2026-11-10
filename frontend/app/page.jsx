"use client";

/**
 * JanMat — SIH 2025, PS SIH25035: sentiment analysis of comments received
 * through an e-consultation on draft legislation (bills tracked by PRS
 * Legislative Research).
 *
 *   - Chatbot about the bills (signed-in users only)
 *   - Public comments on every bill (anyone can read; posting needs sign-in)
 *   - Sentiment dashboard: positive/neutral/negative split, per-comment and
 *     overall summaries, word cloud, per-bill breakdown, CSV export
 *
 * Data is read straight from Supabase with the anon key through public views
 * (see supabase/migration_public_comments.sql and migration_sentiment.sql):
 *   public_bills           title, link and status of each ingested PRS bill
 *   public_comments        every comment + its analysis, author email masked
 *   public_topic_insights  overall summary per bill and for all bills
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { supabase, explainSupabaseError } from "../lib/supabaseClient";
import { useSession } from "../lib/useSession";
import JanMatChatWidget from "../components/JanMatChatWidget";
import AuthWidget from "../components/AuthWidget";
import CommentSection from "../components/CommentSection";
import AllComments from "../components/AllComments";
import InsightsDashboard from "../components/InsightsDashboard";
import { InsightSummary, SentimentBar } from "../components/SentimentParts";
import WordCloud from "../components/WordCloud";

const JANMAT_SPACE_URL = process.env.NEXT_PUBLIC_JANMAT_SPACE_URL || "https://beastzzz-janmat.hf.space";
const COMMENT_FIELDS =
  "id, topic_key, topic_title, body, author_label, created_at, sentiment, sentiment_score, summary, source, source_url";

function Eyebrow({ children }) {
  return <p className="font-mono text-xs tracking-[0.2em] text-marigold uppercase mb-3">{children}</p>;
}

function BillRow({ bill, index, comments, insight, session, onPosted, onAnalyzed }) {
  const [open, setOpen] = useState(false);
  const count = comments.length;
  return (
    <div className="border-b border-paper-line last:border-b-0">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="w-full flex items-center gap-4 py-4 text-left group">
        <span className="font-mono text-xs text-ink-faint w-8 shrink-0">{String(index + 1).padStart(2, "0")}</span>
        <span className="font-display text-lg text-ink flex-1 min-w-0 break-words group-hover:text-marigold transition-colors">
          {bill.title}
        </span>
        {bill.status && (
          <span className="hidden sm:inline font-mono text-[10px] uppercase tracking-wider text-ink-faint border border-paper-line px-2 py-1 rounded-sm shrink-0">
            {bill.status}
          </span>
        )}
        <span className="font-mono text-xs text-ink-faint shrink-0 text-right">
          {count} {count === 1 ? "comment" : "comments"}
        </span>
        <span className={`font-mono text-ink-faint shrink-0 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden>
          →
        </span>
      </button>
      {open && (
        <div className="pb-5 sm:pl-12 space-y-5">
          <a href={bill.url} target="_blank" rel="noreferrer" className="font-mono text-xs underline text-ink-faint">
            Read the bill on PRS
          </a>
          {count > 0 && (
            <div className="space-y-4 border border-paper-line rounded-sm p-4 bg-paper/40">
              <p className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">What commenters think</p>
              <SentimentBar comments={comments} />
              <InsightSummary insight={insight} />
              <WordCloud comments={comments} max={30} />
            </div>
          )}
          <CommentSection
            topicKey={bill.url}
            topicTitle={bill.title}
            comments={comments}
            session={session}
            spaceUrl={JANMAT_SPACE_URL}
            onPosted={onPosted}
            onAnalyzed={onAnalyzed}
          />
        </div>
      )}
    </div>
  );
}

export default function Page() {
  const session = useSession();
  const [bills, setBills] = useState(null);
  const [comments, setComments] = useState(null);
  const [insights, setInsights] = useState({});
  const [error, setError] = useState(null);

  const loadInsights = useCallback(async () => {
    const { data, error: e } = await supabase
      .from("public_topic_insights")
      .select("topic_key, topic_title, overall_summary, key_points, comment_count, updated_at");
    if (e) {
      console.warn("Insights unavailable:", e.message);
      return;
    }
    setInsights(Object.fromEntries((data || []).map((i) => [i.topic_key, i])));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let b, c;
      try {
        [b, c] = await Promise.all([
          supabase.from("public_bills").select("id, title, url, status").order("title"),
          supabase.from("public_comments").select(COMMENT_FIELDS).order("created_at", { ascending: false }).limit(2000),
        ]);
      } catch (e) {
        if (!cancelled) {
          setError(explainSupabaseError(e));
          setBills([]);
          setComments([]);
        }
        return;
      }
      if (cancelled) return;
      if (b.error || c.error) setError(explainSupabaseError(b.error || c.error));
      setBills(b.data || []);
      setComments(c.data || []);
    })();
    loadInsights();
    return () => {
      cancelled = true;
    };
  }, [loadInsights]);

  const commentsByTopic = useMemo(() => {
    const m = new Map();
    (comments || []).forEach((c) => {
      if (!m.has(c.topic_key)) m.set(c.topic_key, []);
      m.get(c.topic_key).push(c);
    });
    return m;
  }, [comments]);

  const addComment = (c) => setComments((prev) => [c, ...(prev || [])]);
  const applyAnalysis = (update) => {
    setComments((prev) => (prev || []).map((c) => (c.id === update.id ? { ...c, ...update } : c)));
    loadInsights(); // the backend has just refreshed this bill's summary
  };

  return (
    <main className="max-w-3xl mx-auto px-4 sm:px-6 py-14">
      <header className="mb-10 border-b-2 border-ink pb-6">
        <p className="font-mono text-xs tracking-[0.2em] text-marigold uppercase mb-2">Public Consultation Register</p>
        <h1 className="font-display text-4xl sm:text-5xl text-ink font-semibold leading-tight">JanMat</h1>
        <p className="font-body text-sm text-ink-faint mt-3 max-w-xl leading-relaxed">
          Comment on draft Indian bills, see how the public feels about each one through AI sentiment analysis,
          summaries and word clouds, and ask our chatbot questions grounded in the bills&apos; actual text.
        </p>
        <div className="mt-4">
          <AuthWidget />
        </div>
      </header>

      <section aria-label="Sentiment dashboard" className="mb-14">
        <Eyebrow>Sentiment Dashboard</Eyebrow>
        <InsightsDashboard comments={comments} insights={insights} loading={comments === null} />
      </section>

      <section aria-label="Ask JanMat" className="mb-14">
        <Eyebrow>Ask a Question</Eyebrow>
        <JanMatChatWidget spaceUrl={JANMAT_SPACE_URL} session={session} />
      </section>

      <section aria-label="Tracked bills" className="mb-14">
        <Eyebrow>Comment on a bill</Eyebrow>
        {bills === null && <p className="font-mono text-xs text-ink-faint">Loading bills…</p>}
        {error && <p className="font-mono text-xs text-seal">{error}</p>}
        {bills && bills.length === 0 && !error && (
          <p className="font-mono text-xs text-ink-faint">
            No bills yet. Run ingestion from the Space&apos;s Admin panel to load them.
          </p>
        )}
        {bills &&
          bills.map((bill, i) => (
            <BillRow
              key={bill.id}
              bill={bill}
              index={i}
              comments={commentsByTopic.get(bill.url) || []}
              insight={insights[bill.url]}
              session={session}
              onPosted={addComment}
              onAnalyzed={applyAnalysis}
            />
          ))}
      </section>

      <section aria-label="Community discussion" className="mb-14">
        <Eyebrow>What people are saying</Eyebrow>
        <AllComments comments={comments} loading={comments === null} error={error} />
      </section>

      <section aria-label="General discussion">
        <CommentSection
          topicKey="janmat:general"
          topicTitle="General discussion"
          comments={comments === null ? null : commentsByTopic.get("janmat:general") || []}
          session={session}
          spaceUrl={JANMAT_SPACE_URL}
          onPosted={addComment}
          onAnalyzed={applyAnalysis}
        />
      </section>

      <footer className="mt-14 pt-6 border-t border-paper-line">
        <p className="font-mono text-[10px] text-ink-faint leading-relaxed">
          Bill texts and commentary are published by PRS Legislative Research and reproduced for non-commercial
          purposes with due acknowledgement, per their reproduction policy. Built for Smart India Hackathon 2025,
          problem statement SIH25035.
        </p>
      </footer>
    </main>
  );
}
