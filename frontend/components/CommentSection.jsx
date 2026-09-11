"use client";

/**
 * Public comments on a bill or article. Reads are open to everyone;
 * posting requires being signed in (enforced both here and by the
 * database's Row Level Security policy, so this isn't just a UI gate).
 *
 * Usage: <CommentSection topicKey="https://prsindia.org/billtrack/..." topicTitle="Some Bill 2026" />
 * topicKey should be a stable identifier for the thing being discussed —
 * the bill/article's URL is a natural choice since it's already unique.
 */
import { useEffect, useState } from "react";
import { supabase } from "../lib/supabaseClient";

export default function CommentSection({ topicKey, topicTitle }) {
  const [session, setSession] = useState(null);
  const [comments, setComments] = useState(null);
  const [body, setBody] = useState("");
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => listener.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadComments() {
      const { data, error: fetchError } = await supabase
        .from("comments")
        .select("id, body, author_email, created_at")
        .eq("topic_key", topicKey)
        .order("created_at", { ascending: false });
      if (!cancelled) {
        if (fetchError) setError(fetchError.message);
        else setComments(data);
      }
    }
    loadComments();
    return () => {
      cancelled = true;
    };
  }, [topicKey]);

  async function postComment(e) {
    e.preventDefault();
    if (!body.trim() || !session) return;
    setPosting(true);
    setError(null);

    const { data, error: insertError } = await supabase
      .from("comments")
      .insert({
        topic_key: topicKey,
        topic_title: topicTitle || null,
        user_id: session.user.id,
        author_email: session.user.email,
        body: body.trim(),
      })
      .select("id, body, author_email, created_at")
      .single();

    setPosting(false);
    if (insertError) {
      setError(insertError.message);
      return;
    }
    setComments((prev) => [data, ...(prev || [])]);
    setBody("");
  }

  return (
    <div className="border-t border-paper-line pt-6 mt-6">
      <p className="font-mono text-xs tracking-[0.2em] text-marigold uppercase mb-3">
        Public Comments {comments ? `(${comments.length})` : ""}
      </p>

      {session ? (
        <form onSubmit={postComment} className="mb-5">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Share your view on this bill or article..."
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
        <p className="font-mono text-xs text-ink-faint mb-5">Sign in above to post a comment.</p>
      )}

      {error && <p className="font-mono text-xs text-seal mb-3">{error}</p>}

      {comments === null && <p className="font-mono text-xs text-ink-faint">Loading comments...</p>}

      {comments && comments.length === 0 && (
        <p className="font-mono text-xs text-ink-faint">No comments yet — be the first to weigh in.</p>
      )}

      {comments && comments.length > 0 && (
        <ul className="space-y-3">
          {comments.map((c) => (
            <li key={c.id} className="border border-paper-line rounded-sm px-3 py-2 bg-paper/60">
              <div className="flex items-baseline justify-between gap-2 mb-1">
                <span className="font-mono text-[10px] text-ink-faint">{c.author_email}</span>
                <span className="font-mono text-[10px] text-ink-faint">
                  {new Date(c.created_at).toLocaleDateString()}
                </span>
              </div>
              <p className="text-sm font-body text-ink whitespace-pre-wrap">{c.body}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
