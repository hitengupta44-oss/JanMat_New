"use client";

/**
 * JanMat: chat + public comments on every tracked bill.
 *
 * Bills and comments are read straight from Supabase with the anon key,
 * through two public views (see supabase/migration_public_comments.sql):
 *   public_bills     title, link and status of each ingested bill
 *   public_comments  every comment, with the author's email masked
 * Everyone can read them without signing in; posting needs an account.
 */
import { useEffect, useMemo, useState } from "react";
import { supabase, explainSupabaseError } from "../lib/supabaseClient";
import JanMatChatWidget from "../components/JanMatChatWidget";
import AuthWidget from "../components/AuthWidget";
import CommentSection from "../components/CommentSection";
import AllComments from "../components/AllComments";

const JANMAT_SPACE_URL = process.env.NEXT_PUBLIC_JANMAT_SPACE_URL || "https://beastzzz-janmat.hf.space";

function BillRow({ bill, index, count, onPosted }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-paper-line last:border-b-0">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="w-full flex items-center gap-4 py-4 text-left group">
        <span className="font-mono text-xs text-ink-faint w-8 shrink-0">{String(index + 1).padStart(2, "0")}</span>
        <span className="font-display text-lg text-ink flex-1 group-hover:text-marigold transition-colors">{bill.title}</span>
        {bill.status && (
          <span className="hidden sm:inline font-mono text-[10px] uppercase tracking-wider text-ink-faint border border-paper-line px-2 py-1 rounded-sm shrink-0">
            {bill.status}
          </span>
        )}
        <span className="font-mono text-xs text-ink-faint shrink-0 w-28 text-right">
          {count} {count === 1 ? "comment" : "comments"}
        </span>
        <span className={`font-mono text-ink-faint shrink-0 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden>
          →
        </span>
      </button>
      {open && (
        <div className="pb-5 pl-12">
          <a href={bill.url} target="_blank" rel="noreferrer" className="font-mono text-xs underline text-ink-faint">
            Read the bill on PRS
          </a>
          <CommentSection topicKey={bill.url} topicTitle={bill.title} onPosted={onPosted} />
        </div>
      )}
    </div>
  );
}

export default function Page() {
  const [bills, setBills] = useState(null);
  const [comments, setComments] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let b, c;
      try {
        [b, c] = await Promise.all([
        supabase.from("public_bills").select("id, title, url, status").order("title"),
        supabase
          .from("public_comments")
          .select("id, topic_key, topic_title, body, author_label, created_at")
          .order("created_at", { ascending: false })
          .limit(1000),
        ]);
      } catch (e) {
        // Network-level failure (supabase-js normally returns {error}, but be safe).
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
    return () => {
      cancelled = true;
    };
  }, []);

  const counts = useMemo(() => {
    const m = new Map();
    (comments || []).forEach((c) => m.set(c.topic_key, (m.get(c.topic_key) || 0) + 1));
    return m;
  }, [comments]);

  const addComment = (c) => setComments((prev) => [c, ...(prev || [])]);

  return (
    <main className="max-w-3xl mx-auto px-6 py-14">
      <header className="mb-10 border-b-2 border-ink pb-6">
        <p className="font-mono text-xs tracking-[0.2em] text-marigold uppercase mb-2">Public Consultation Register</p>
        <h1 className="font-display text-4xl sm:text-5xl text-ink font-semibold leading-tight">JanMat</h1>
        <p className="font-body text-sm text-ink-faint mt-3 max-w-xl leading-relaxed">
          Ask questions about Indian bills and get answers grounded in their actual text, and read what
          citizens are saying about every bill.
        </p>
        <div className="mt-4">
          <AuthWidget />
        </div>
      </header>

      <section aria-label="Ask JanMat" className="mb-14">
        <p className="font-mono text-xs tracking-[0.2em] text-marigold uppercase mb-3">Ask a Question</p>
        <JanMatChatWidget spaceUrl={JANMAT_SPACE_URL} />
      </section>

      <section aria-label="Community discussion" className="mb-14">
        <p className="font-mono text-xs tracking-[0.2em] text-marigold uppercase mb-3">What people are saying</p>
        <AllComments comments={comments} loading={comments === null} error={error} />
      </section>

      <section aria-label="Tracked bills" className="mb-14">
        <p className="font-mono text-xs tracking-[0.2em] text-marigold uppercase mb-3">Comment on a bill</p>
        {bills === null && <p className="font-mono text-xs text-ink-faint">Loading bills…</p>}
        {error && <p className="font-mono text-xs text-seal">{error}</p>}
        {bills && bills.length === 0 && !error && (
          <p className="font-mono text-xs text-ink-faint">
            No bills yet. Run ingestion from the Space&apos;s Admin panel to load them.
          </p>
        )}
        {bills && bills.map((bill, i) => (
          <BillRow key={bill.id} bill={bill} index={i} count={counts.get(bill.url) || 0} onPosted={addComment} />
        ))}
      </section>

      <section aria-label="General discussion">
        <CommentSection topicKey="janmat:general" topicTitle="General discussion" onPosted={addComment} />
      </section>

      <footer className="mt-14 pt-6 border-t border-paper-line">
        <p className="font-mono text-[10px] text-ink-faint leading-relaxed">
          Bill texts and commentary are published by PRS Legislative Research and reproduced for
          non-commercial purposes with due acknowledgement, per their reproduction policy.
        </p>
      </footer>
    </main>
  );
}
