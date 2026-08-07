import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// Next.js 16 renamed `middleware.ts` to `proxy.ts` (the exported function
// too) — this file is that, not the old convention. See the "Migration to
// Proxy" section of the framework's own docs.
//
// Runs before every route: refreshes the Supabase session (writing any
// renewed cookies back to the response) and gates access — this is the
// actual enforcement point for "must be signed in to use Content Studio."

const PUBLIC_PATHS = ["/login"];

// The landing page ("/") is also public, but as an EXACT match only — a
// prefix check here (`pathname.startsWith("/")`) would make every route in
// the app public, since every path starts with "/". Kept separate from
// PUBLIC_PATHS (which uses startsWith, correctly, for "/login" and any
// future nested public routes) so this exact-match requirement can't
// silently get "simplified" into the same broken prefix check later.
const PUBLIC_EXACT_PATHS = ["/"];

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          response = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
        },
      },
    },
  );

  // getUser() (not getSession()) — revalidates against Supabase itself
  // rather than trusting whatever the cookie claims, per Supabase's own
  // guidance for exactly this proxy/middleware checkpoint.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const isPublicPath =
    PUBLIC_EXACT_PATHS.includes(pathname) || PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  if (!user && !isPublicPath) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("redirectTo", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Only bounce a signed-in visitor off /login (finishing sign-in should
  // land them in the app) — NOT off "/", so a signed-in user can still
  // deliberately visit the public landing page (e.g. to grab a link).
  if (user && PUBLIC_PATHS.some((path) => pathname.startsWith(path))) {
    const homeUrl = request.nextUrl.clone();
    homeUrl.pathname = "/chat";
    homeUrl.search = "";
    return NextResponse.redirect(homeUrl);
  }

  return response;
}

export const config = {
  matcher: [
    // Everything except static assets and image optimization — those
    // don't need a session check and shouldn't be slowed down by one.
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
