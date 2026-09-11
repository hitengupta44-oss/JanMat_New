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
