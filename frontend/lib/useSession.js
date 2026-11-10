"use client";

import { useEffect, useState } from "react";
import { supabase } from "./supabaseClient";

/** Current Supabase Auth session (null when signed out), kept in sync with sign-in/out. */
export function useSession() {
  const [session, setSession] = useState(null);
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => listener.subscription.unsubscribe();
  }, []);
  return session;
}
