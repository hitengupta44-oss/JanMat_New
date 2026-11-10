"use client";

/**
 * Public comments on one bill (the e-consultation). Reading is open to
 * everyone; posting needs a signed-in account (enforced here and by the
 * database's Row Level Security policy, so it isn't just a UI gate).
 *
 * Right after a comment is posted, the backend is asked to analyse it
 * (sentiment + one-line summary, and a refreshed bill summary). The result
 * shows up on the comment as soon as it's ready.
 *
 * The page owns the list of comments and passes this bill's in, so a new
 * comment or its analysis shows up everywhere (dashboard, lists) at once.
 */
import { useState } from "react";
import { supabase, explainSupabaseError } from "../lib/supabaseClient";
import { callGradioApi } from "../lib/gradio";
import { SentimentBadge } from "./SentimentParts";

export function maskEmail(email = "") {
  const [name = "", domain = ""] = email.split("@");
  return `${name.length > 2 ? name.slice(0, 2) : ""}***@${domain}`;
}

export function CommentItem({ c, showBill = false }) {
  return (
    <li className="border border-paper-line rounded-sm px-3 py-2 bg-paper/60">
      {showBill && (
        <p className="font-mono text-[10px] uppercase tracking-wider text-marigold mb-1 break-words">
          {c.topic_title || "General discussion"}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <SentimentBadge sentiment={c.sentiment} score={c.sentiment_score} />
        <span className="font-mono text-[10px] text-ink-faint">
          {c.author_label} · {new Date(c.created_at).toLocaleDateString()}
        </span>
      </div>
      <p className="text-sm font-body text-ink whitespace-pre-wrap">{c.body}</p>
      {c.summary && (
        <p className="font-body text-xs text-ink-faint mt-1.5 border-l-2 border-paper-line pl-2">
          <span className="font-mono uppercase tracking-wider text-[10px]">Summary: </span>
          {c.summary}
        </p>
      )}
    </li>
  );
}

export default function CommentSection({ topicKey, topicTitle, comments, session, spaceUrl, onPosted, onAnalyzed }) {
  const [body, setBody] = useState("");
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);

  async function analyse(commentId) {
    try {
      const result = await callGradioApi(spaceUrl, "analyze_comment", [String(commentId), session.access_token]);
      const r = Array.isArray(result) ? result[0] : result;
      if (r && r.ok) {
        onAnalyzed?.({ id: commentId, sentiment: r.sentiment, sentiment_score: r.score, summary: r.summary });
        setNote(null);
      } else {
        setNote("Your comment is posted. Its sentiment analysis will appear later.");
      }
    } catch (e) {
      console.warn("Comment analysis failed:", e);
      setNote("Your comment is posted. Its sentiment analysis will appear later.");
    }
  }

  async function postComment(e) {
    e.preventDefault();
    if (!body.trim() || !session) return;
    setPosting(true);
    setError(null);
    setNote(null);

    const { data, error: insertError } = await supabase
      .from("comments")
      .insert({
        topic_key: topicKey,
        topic_title: topicTitle || null,
        user_id: session.user.id,
        author_email: session.user.email,
        body: body.trim(),
      })
      .select("id, topic_key, topic_title, body, author_email, created_at")
      .single();

    setPosting(false);
    if (insertError) {
      setError(explainSupabaseError(insertError));
      return;
    }
    onPosted?.({
      id: data.id,
      topic_key: data.topic_key,
      topic_title: data.topic_title,
      body: data.body,
      created_at: data.created_at,
      author_label: maskEmail(data.author_email),
      sentiment: null,
      sentiment_score: null,
      summary: null,
    });
    setBody("");
    analyse(data.id); // runs in the background; the badge updates when it's done
  }

  const list = comments || [];

  return (
    <div className="border-t border-paper-line pt-6 mt-6">
      <p className="font-mono text-xs tracking-[0.2em] text-marigold uppercase mb-3">
        Public Comments {comments ? `(${list.length})` : ""}
      </p>

      {session ? (
        <form onSubmit={postComment} className="mb-5">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Share your view on this bill…"
            maxLength={3000}
            rows={3}
            className="w-full border border-paper-line rounded-sm px-3 py-2 text-sm font-body bg-paper resize-none"
          />
          <div className="flex items-center justify-between mt-2">
            <span className="font-mono text-[10px] text-ink-faint">{body.length}/3000</span>
            <button
              type="submit"
              disabled={posting || !body.trim()}
              className="bg-ink text-paper rounded-sm px-4 py-1.5 text-xs font-mono uppercase tracking-wide disabled:opacity-50"
            >
              {posting ? "Posting..." : "Post comment"}
            </button>
          </div>
        </form>
      ) : (
        <p className="font-mono text-xs text-ink-faint mb-5">🔒 Sign in at the top of the page to post a comment.</p>
      )}

      {error && <p className="font-mono text-xs text-seal mb-3">{error}</p>}
      {note && <p className="font-mono text-xs text-ink-faint mb-3">{note}</p>}

      {comments === null && <p className="font-mono text-xs text-ink-faint">Loading comments...</p>}
      {comments && list.length === 0 && (
        <p className="font-mono text-xs text-ink-faint">No comments yet — be the first to weigh in.</p>
      )}
      {list.length > 0 && (
        <ul className="space-y-3">
          {list.map((c) => (
            <CommentItem key={c.id} c={c} />
          ))}
        </ul>
      )}
    </div>
  );
}
