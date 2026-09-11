"use client";

/**
 * Simple email login — Supabase Auth's magic link flow, no passwords to
 * manage. Shows a sign-in form when logged out, and the user's email +
 * a sign-out button when logged in.
 *
 * Usage: <AuthWidget /> — put it once near the top of the page. Other
 * components (like CommentSection) read the session directly from
 * supabase.auth themselves, so they stay in sync automatically.
 */
import { useEffect, useState } from "react";
import { supabase } from "../lib/supabaseClient";

export default function AuthWidget() {
  const [session, setSession] = useState(null);
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("idle"); // idle | sending | sent | error
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  async function sendMagicLink(e) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("sending");
    setErrorMsg("");
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: typeof window !== "undefined" ? window.location.origin : undefined },
    });
    if (error) {
      setStatus("error");
      setErrorMsg(error.message);
    } else {
      setStatus("sent");
    }
  }

  async function signOut() {
    await supabase.auth.signOut();
  }

  if (session) {
    return (
      <div className="flex items-center gap-3 font-mono text-xs text-ink-faint">
        <span>Signed in as {session.user.email}</span>
        <button onClick={signOut} className="underline hover:text-ink">
          Sign out
        </button>
      </div>
    );
  }

  if (status === "sent") {
    return (
      <p className="font-mono text-xs text-moss">
        Check {email} for a sign-in link.
      </p>
    );
  }

  return (
    <form onSubmit={sendMagicLink} className="flex items-center gap-2">
      <input
        type="email"
        required
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="border border-paper-line rounded-sm px-2 py-1 text-xs font-body bg-paper"
      />
      <button
        type="submit"
        disabled={status === "sending"}
        className="bg-ink text-paper rounded-sm px-3 py-1 text-xs font-mono uppercase tracking-wide disabled:opacity-50"
      >
        {status === "sending" ? "Sending..." : "Sign in"}
      </button>
      {status === "error" && <span className="text-xs text-seal">{errorMsg}</span>}
    </form>
  );
}
