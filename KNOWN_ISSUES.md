# Known Issues & Incomplete States

Audit compiled from this build session (Trend Analyzer → Company Analyzer →
Knowledge Base → Trend Matching), verified live against a real (throwaway
SQLite) database and a running frontend/backend, plus static review of
what's still stubbed or deferred. Current repo state: branch
`business-analyzer`, HEAD `8b4a1d4`.

**Backend tests: 84/84 passing. Frontend: lint/typecheck/build all clean.**
Everything below is what those green checks don't cover.

Of everything actionable from the previous round, only two items remain —
both explicitly deferred **by your choice**, not because they're stuck:
Postgres migration testing (no credentials available here) and auth (you
chose to skip it for this pass). Everything else that was fixable without
those has been fixed and verified live.

---

## ✅ Resolved this round

| # | Issue | Fix | Commit |
|---|---|---|---|
| 1 | No distinct signal when a company's website scraped fine but no profile could be extracted (missing `ANTHROPIC_API_KEY`) — silently showed `status: "complete"` with every field blank | New `complete_no_profile` status; `extract_company_profile()` now returns `(profile, extracted_ok)` so the graph can tell the cases apart. Verified live. | `8ecd9f2` |
| 2 | (Found while fixing #1) Multi-line JSX text adjacent to `{expr}` silently drops its leading space — a real, if subtle, JSX whitespace-collapsing bug | Rewrote the new status message as a single template-literal expression | `8ecd9f2` |
| 3 | **Google Trends collector was 100% non-functional** — confirmed Google deprecated/moved its whole legacy "unofficial internal API" surface (`trending_searches`, `today_searches`, `realtime_trending_searches` all 404), not just the one endpoint flagged previously | Rewrote on `related_queries()['rising']` against configurable seed keywords — the still-live `explore` API. Verified live: 34 real trending items, zero errors (previously 100% failure). | `8b4a1d4` |

## ✅ Resolved previous round (carried forward for context)

SSRF protection, stray test artifacts, document accumulation on
re-onboarding, URL normalization, dead `numpy` dependency, Reddit's
public-JSON collector replaced with PRAW/OAuth — see commits `8722946`,
`7acf5d2`, `51ba50e`, `188c910`.

**Every collector now either returns real live data (RSS, Google Trends)
or fails cleanly with zero errors when ungated (Instagram/TikTok/
Twitter/YouTube skip gracefully without credentials) — none are silently
broken anymore.** Reddit specifically still needs a real app registration
to verify PRAW end-to-end (see below).

---

## 🔴 Remaining: deferred by your explicit choice, not blocked

### No auth on any endpoint
You chose "skip auth for now" when asked. Still true — `/companies`,
`/trend-analyzer/*`, `/knowledge-base/search` are all open. Fine for local
dev; **must** land before any non-local deployment. Recommended approach
when you're ready: Supabase Auth (already your DB provider, no new
service, JWT + RLS built in) — this also directly fixes the single-tenant
Trend Matching limitation below (a company would belong to a user).

### Migration `0002_kb_and_companies.py` still untested against real Postgres
You chose to skip providing credentials for this pass. All verification
has used SQLite (`Base.metadata.create_all()`), which bypasses Alembic
entirely. The Postgres-specific paths (`CREATE EXTENSION vector`,
`ARRAY(String())`, `Vector(1024)`, the IVFFlat index) — plus the new
migration `0003` from this round — have never actually run against real
Postgres. Whenever you have a connection string, `alembic upgrade head`
against it is the single highest-value remaining check.

---

## 🟡 Remaining: needs a product/design decision, not just a fix

- **Single-tenant assumption in Trend Matching.** `score_relevance` in
  `trend_analyzer/graph.py` scores trends against "the most recently
  updated `complete` Company" — with 2+ companies onboarded, trends get
  scored against whichever was touched most recently, silently, no error.
  Real fix is multi-tenancy tied to auth — out of scope until that lands.

---

## 🟡 External-source fragility (verified live — not code bugs)

- **YouTube, X/Twitter, Instagram, TikTok** collectors have never been
  tested against live credentials (none are configured anywhere) — only
  verified via mocked tests + the "skip gracefully" path.
- **Reddit** now uses PRAW/OAuth but has likewise never been tested
  against a real Reddit app registration — only mocked.
- **RSS and Google Trends** are the only two sources confirmed returning
  real data end-to-end, live, this session.

---

## ⚪ Incomplete / deferred features (by design — see TODO.md for full detail)

**Phase 1 — Foundation**
- CI/CD pipeline: not started
- Auth (JWT/OAuth), RBAC, user registration, API key management: not started (see above — your call to defer)
- Task queue (Celery+Redis): deliberately not used — APScheduler in-process instead (documented tradeoff, revisit at scale)
- WebSocket real-time updates: not started
- Logging/monitoring/error tracking (Sentry): not started
- Vector DB: **done** (pgvector on Supabase)

**Phase 2 — Knowledge Base**
- Social media profile importer, dedicated blog/article indexer, dedicated product-page parser, document uploader (PDF/DOCX): not built
- KB dashboard UI, freshness indicators, automatic incremental re-indexing, manual data entry UI: not built
- Search endpoint exists (`GET /knowledge-base/search`); no dedicated search UI page

**Phase 3 — Company Analyzer**
- Competitor Research Agent: not started (whole subsystem)
- Knowledge Manager Agent (distinct from the underlying KB infra): not started
- Products & services cataloging as a distinct extracted field: not built (captured only implicitly in scraped content + summary)
- Onboarding is URL-only by design (no multi-step wizard) — explicit decision, not a gap

**Phase 4 — Trend Analyzer**
- LinkedIn collector: not attempted (no public API without Marketing Partner status; would require scraping)
- Trend Matching: campaign history comparison, competitor activity correlation, proactive recommendation engine — all deferred, need modules that don't exist yet (Phase 5 campaign history, Competitor Research Agent)
- Performance Discovery: not started at all (needs campaign history)
- Trend Outputs: weekly report generator, insights summarizer, content opportunity recommender, alerts/notifications — not built (only the raw feed + relevance filter exist)

**Phases 5–8 — Content Management, Social Media Analyzer, Integration/Polish, Future Expansion**
- Entirely unbuilt. Only placeholder `{"status": "active"}` responses exist at `/api/v1/content-management` and `/api/v1/social-media-analyzer`.

---

## Next steps, roughly in priority order

1. Whenever you're ready to unblock the two deferred items: share a
   Postgres connection string (or run `alembic upgrade head` yourself),
   and let me know when you want to start on auth — Supabase Auth is the
   recommendation, and it resolves the single-tenant Trend Matching gap
   as a side effect.
2. Get real credentials for at least one of YouTube/X/Instagram/TikTok/
   Reddit to validate a collector end-to-end beyond the mocked test suite
   — RSS and Google Trends are proven live now; the rest are still only
   proven-to-skip-gracefully.
