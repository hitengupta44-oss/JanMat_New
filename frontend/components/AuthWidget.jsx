"use client";

/**
 * Email + password authentication.
 *
 * Chosen over magic links because Supabase's built-in email service is
 * rate-limited to a handful of messages per hour (it's intended for
 * development, not production), which made magic links unusable without
 * configuring an external SMTP provider. Password auth sends no email at
 * all on sign-in, so there's no limit to hit — and it's faster for the
 * user, who doesn't have to leave the page to check an inbox.
 *
 * NOTE: for sign-up to work without email, "Confirm email" must be turned
 * OFF in Supabase → Authentication → Sign In / Providers → Email. If it's
 * left on, Supabase still sends a confirmation email and the account stays
 * unusable until it's clicked — which reintroduces the rate limit problem.
 *
 * Usage: <AuthWidget /> — place once near the top of the page. Other
 * components (CommentSection) read the session from supabase.auth directly,
 * so they stay in sync automatically.
 */
import { useEffect, useState } from "react";
import { supabase } from "../lib/supabaseClient";

export default function AuthWidget() {
  const [session, setSession] = useState(null);
  const [mode, setMode] = useState("signin"); // "signin" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null); // { type: "error" | "success", text }

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    const cleanEmail = email.trim();
    if (!cleanEmail || !password) return;

    if (mode === "signup" && password.length < 6) {
      setMessage({ type: "error", text: "Password must be at least 6 characters." });
      return;
    }

    setBusy(true);
    setMessage(null);

    try {
      if (mode === "signup") {
        const { data, error } = await supabase.auth.signUp({
          email: cleanEmail,
          password,
        });
        if (error) throw error;

        // A user with no session means one of two things, and Supabase
        // deliberately doesn't distinguish them (it's an anti-enumeration
        // measure so attackers can't probe which emails are registered):
        //   1. email confirmation is enabled and a mail was sent, or
        //   2. this email is ALREADY registered.
        // Case 2 is the common one in practice, so the message covers both
        // rather than sending people to an inbox that will stay empty.
        if (data.user && !data.session) {
          setMessage({
            type: "error",
            text:
              "That email may already be registered — try signing in. " +
              "(If your account was set up before passwords were enabled, ask the admin to remove it so you can re-register.)",
          });
        } else {
          setMessage({ type: "success", text: "Account created — you're signed in." });
          setPassword("");
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email: cleanEmail,
          password,
        });
        if (error) throw error;
        setPassword("");
      }
    } catch (err) {
      const raw = err?.message || "Something went wrong. Please try again.";
      // Supabase's wording here is opaque to end users.
      const friendly = /invalid login credentials/i.test(raw)
        ? "Wrong email or password. If you haven't registered yet, choose Create account."
        : /already registered/i.test(raw)
        ? "That email is already registered — try signing in instead."
        : raw;
      setMessage({ type: "error", text: friendly });
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    await supabase.auth.signOut();
    setMessage(null);
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

  return (
    <div className="space-y-2">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-2">
        <input
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="border border-paper-line rounded-sm px-2 py-1 text-xs font-body bg-paper"
        />
        <input
          type="password"
          required
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="border border-paper-line rounded-sm px-2 py-1 text-xs font-body bg-paper"
        />
        <button
          type="submit"
          disabled={busy}
          className="bg-ink text-paper rounded-sm px-3 py-1 text-xs font-mono uppercase tracking-wide disabled:opacity-50"
        >
          {busy ? "..." : mode === "signup" ? "Create account" : "Sign in"}
        </button>
        <button
          type="button"
          onClick={() => {
            setMode(mode === "signup" ? "signin" : "signup");
            setMessage(null);
          }}
          className="font-mono text-[11px] text-ink-faint underline hover:text-ink"
        >
          {mode === "signup" ? "Have an account? Sign in" : "New here? Create account"}
        </button>
      </form>

      {message && (
        <p
          className={
            "font-mono text-[11px] " + (message.type === "error" ? "text-seal" : "text-moss")
          }
        >
          {message.text}
        </p>
      )}
    </div>
  );
}
