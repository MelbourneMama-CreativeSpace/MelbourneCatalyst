# Credentials Required to Operate MMCS Social Network

Every credential below is something **you** register and paste into an
`.env` file — this assistant never handles, generates, or has access to
your actual keys/secrets. This doc just tells you what to go get, where
to get it, and what breaks if you skip it.

Backend variables go in `backend/.env` (copy `backend/.env.example` as a
starting point). Frontend needs one variable in `frontend/.env.local`.

---

## Quick summary

| Tier | What it unlocks | App usable without it? |
|---|---|---|
| 1. Core | Every AI agent + persistent storage + semantic search | No — agents silently no-op, KB search returns nothing |
| 2. Trend sources | More trend-discovery coverage (Reddit, YouTube, X, Instagram, TikTok) | Yes — Google Trends + RSS work with zero credentials |
| 3. Platform OAuth | "Connect your account" buttons for Phase 6 (Facebook, Instagram, X, LinkedIn, TikTok, YouTube) | Yes — but see the caveat under Tier 3, this doesn't yet pull real analytics either way |
| 4. Not used | Declared in config but no code path reads them | N/A |

---

## Tier 1 — Required for a functioning app

Without these, the app boots and the UI loads, but every AI-driven
feature returns an empty/failed result and Knowledge Base search finds
nothing.

### `DATABASE_URL` — Postgres connection string
- **What it's for:** all persistent data — companies, trends, strategies, content plans, campaigns, everything.
- **Where to get it:** [Supabase](https://supabase.com) → New Project → Project Settings → Database → Connection string (choose the "asyncpg"-compatible URI format, or any Postgres works).
- **Format:** `postgresql+asyncpg://postgres:<password>@<project>.supabase.co:5432/postgres`
- **Then run migrations:** `cd backend && alembic upgrade head` (11 migrations as of this round).

### `ANTHROPIC_API_KEY` — Claude API key
- **What it's for:** every generation step — company profile extraction, strategy consultant, content planner, campaign manager, brand collaboration, trend reports, knowledge audits, competitor comparisons. This is the single most load-bearing credential in the app.
- **Where to get it:** [console.anthropic.com](https://console.anthropic.com) → API Keys.
- **Without it:** every "Generate…" action in the UI completes with `status: "failed"` — no crash, just nothing useful.

### `VOYAGE_API_KEY` — Voyage AI embeddings
- **What it's for:** turning ingested documents (website pages, blog posts, uploaded PDFs/DOCX) into searchable vectors for the Knowledge Base.
- **Where to get it:** [dash.voyageai.com](https://dash.voyageai.com) → API Keys. Free tier: 200M tokens/month, Anthropic's recommended embedding provider.
- **Without it:** documents still get scraped/uploaded and stored, but Knowledge Base search returns nothing (nothing gets embedded).

---

## Tier 2 — Trend Discovery sources (each optional, independent)

Google Trends and RSS feeds work today with **zero credentials** — the
rest are additional sources you can enable one at a time. Skipping all
of these just means fewer trend sources feed the Trend Analyzer; nothing
breaks.

| Source | Variables | Where to get it | Notes |
|---|---|---|---|
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → create a "script" app | Free, read-only OAuth |
| YouTube | `YOUTUBE_API_KEY` | [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) → enable "YouTube Data API v3" → API key | Free tier is generous |
| X / Twitter | `TWITTER_BEARER_TOKEN` | [developer.twitter.com](https://developer.twitter.com/en/portal/dashboard) | **Needs a paid API tier** — the free tier can't search |
| Instagram | `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID` | [developers.facebook.com/apps](https://developers.facebook.com/apps) | Needs a Business/Creator IG account behind a Meta app |
| TikTok | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | [developers.tiktok.com](https://developers.tiktok.com/apps) | Research API — gated behind academic/institutional approval, hardest one to actually get |

`RSS_FEED_URLS`, `GOOGLE_TRENDS_SEED_KEYWORDS`, `REDDIT_SUBREDDITS`, etc.
are not credentials — they're just config lists you can edit directly
in `.env`, defaults already work.

---

## Tier 3 — Social Media Analyzer: Platform Integration (via Composio)

These power the **"Connect"** buttons on the dedicated
`/integrations/[companyId]` page (Phase 6). OAuth is brokered through
[Composio](https://composio.dev) rather than this app talking to each
platform directly — Composio custodies the actual tokens, this backend
only stores a reference id. Each platform is still a separate developer
app registration underneath, all optional and independent — connect
only the platforms you actually use.

**Important caveat before you spend time on these:** connecting an
account today only proves the connection handshake works. The
metrics-fetching agents downstream (Performance Tracking, Social
Analytics, Channel Intelligence) are not built yet — they need a real
connected account to build the response-parsing logic against, which is
exactly why they're not built. So Tier 3 is worth doing when you're
ready to unblock *that* next round of development, not because it
delivers analytics today.

### Two-step setup, not one

**Step 1 — get a Composio account.**
- **`COMPOSIO_API_KEY`** — sign up at [app.composio.dev](https://app.composio.dev), grab your account API key.
- **`FRONTEND_BASE_URL`** — where the browser lands after a connection completes (your deployed frontend URL). `http://localhost:3000` for local testing.

**Step 2 — for each platform you want, register that platform's own
developer app (same registrations as before — Composio doesn't remove
this step), then create a Composio "auth config" in Composio's
dashboard using `use_custom_auth`, pasting that platform's client
ID/secret in *there*, not in this app's `.env`.** Composio's dashboard
gives you back an auth config id (looks like `ac_xxxx`) — that's what
goes in `.env`:

| Platform(s) | `.env` variable | Register the underlying app at |
|---|---|---|
| Instagram | `COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID` | [developers.facebook.com/apps](https://developers.facebook.com/apps) — one Meta app can cover both Instagram and Facebook |
| Facebook | `COMPOSIO_FACEBOOK_AUTH_CONFIG_ID` | same Meta app as above — use the same auth config id in both settings if so |
| X / Twitter | `COMPOSIO_TWITTER_AUTH_CONFIG_ID` | [developer.twitter.com](https://developer.twitter.com/en/portal/dashboard) — separate from the Tier 2 bearer token above |
| LinkedIn | `COMPOSIO_LINKEDIN_AUTH_CONFIG_ID` | [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps) |
| TikTok | `COMPOSIO_TIKTOK_AUTH_CONFIG_ID` | [developers.tiktok.com](https://developers.tiktok.com/apps) — "Login Kit" product, separate from the Tier 2 Research API |
| YouTube | `COMPOSIO_YOUTUBE_AUTH_CONFIG_ID` | [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials) — OAuth client, not the API key from Tier 2. Usually the fastest one to set up. |

Nothing in this app's own code accepts a raw client ID/secret anymore —
that pairing only ever lives in Composio's dashboard.

---

## Tier 4 — Declared but not currently used

Safe to leave blank. Listed only so you don't waste time chasing them.

| Variable | Status |
|---|---|
| `OPENAI_API_KEY` | Declared in `config.py`, no code path reads it — the app is Claude-only. |
| `REDIS_URL` | Reserved for a planned Celery/Redis task queue that doesn't exist yet. |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY` | Optional [LangSmith](https://smith.langchain.com) tracing for debugging the LangGraph pipelines — purely observability, nothing depends on it. |

---

## Frontend

One variable, in `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Defaults to `http://localhost:8000` if unset — only needs setting when
the frontend and backend aren't on the same host (e.g. a real
deployment).

---

## Recommended order if starting from zero

1. **Supabase Postgres** (`DATABASE_URL`) + run `alembic upgrade head` — nothing works without storage.
2. **`ANTHROPIC_API_KEY`** — unlocks every AI agent at once, biggest bang for the buck.
3. **`VOYAGE_API_KEY`** — unlocks Knowledge Base search, free tier is generous.
4. At this point the app is fully functional for Company Analyzer, Trend Analyzer (Google Trends + RSS only), and Content Management.
5. Add Tier 2 trend sources incrementally as you want broader trend coverage — YouTube is the easiest.
6. Tackle Tier 3 (Platform OAuth) only when you're ready to also pick up the Performance Tracking build-out that depends on it — Google/YouTube is typically the least-gated to register first.
