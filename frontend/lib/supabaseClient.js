/**
 * Browser-side Supabase client — used ONLY for auth (email magic link) and
 * the public `comments` table. This is intentionally separate from the
 * backend's service-role access: this client uses the anon key, which is
 * safe to expose in the browser because every table it touches has Row
 * Level Security policies (see supabase/schema.sql) that enforce who can
 * read/write what. It never touches `documents` or `chunks` directly.
 */
import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.warn(
    "NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set — " +
      "login and comments will not work until these are added in Vercel project settings."
  );
}

export const supabase = createClient(SUPABASE_URL || "", SUPABASE_ANON_KEY || "");

export const supabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

/**
 * Turn a raw Supabase/fetch error into something a human can act on.
 * "Failed to fetch" means the browser never got an answer from Supabase at all:
 * wrong/missing NEXT_PUBLIC_SUPABASE_URL (it is baked in at build time, so changing it
 * needs a redeploy), or a free-tier project that auto-paused after 7 idle days.
 */
export function explainSupabaseError(err) {
  const msg = typeof err === "string" ? err : err?.message || "Unknown error";
  if (!supabaseConfigured) {
    return "Supabase is not configured: set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in Vercel, then redeploy.";
  }
  if (/failed to fetch|networkerror|load failed/i.test(msg)) {
    return "Can't reach the database. If you run this site: check that the Supabase project isn't paused (free projects pause after 7 idle days) and that NEXT_PUBLIC_SUPABASE_URL is correct, then redeploy.";
  }
  if (/relation .* does not exist|schema cache|public_(bills|comments)/i.test(msg)) {
    return "The public comment views are missing. Run supabase/migration_public_comments.sql in the Supabase SQL editor.";
  }
  return msg;
}
