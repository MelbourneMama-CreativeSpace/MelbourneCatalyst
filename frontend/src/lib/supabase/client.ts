"use client";

import { createBrowserClient } from "@supabase/ssr";

// A singleton per browser tab — createBrowserClient already memoizes
// internally, but keeping our own reference makes the "why is this
// safe to call repeatedly" obvious at the call sites.
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
