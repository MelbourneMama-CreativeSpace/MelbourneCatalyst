import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

// A fresh client per request — never share this across requests, per
// @supabase/ssr's own docs. Server Components can't write cookies during
// render (Next.js throws), so `setAll` is best-effort there; proxy.ts is
// what actually persists a refreshed session back to the browser.
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            for (const { name, value, options } of cookiesToSet) {
              cookieStore.set(name, value, options);
            }
          } catch {
            // Called from a Server Component during render, where Next.js
            // doesn't allow writing cookies — safe to ignore as long as
            // proxy.ts is refreshing the session on every navigation.
          }
        },
      },
    },
  );
}
