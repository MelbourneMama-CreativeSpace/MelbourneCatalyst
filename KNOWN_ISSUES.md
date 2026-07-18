# Known Issues & Incomplete States

Audit compiled from this build session (Trend Analyzer → Company Analyzer →
Knowledge Base → Trend Matching), verified live against a real (throwaway
SQLite) database and a running frontend/backend, plus static review of
what's still stubbed or deferred. Current repo state: branch
`business-analyzer`, HEAD `188c910`.

**Backend tests: 81/81 passing. Frontend: lint/typecheck/build all clean.**
Everything below is what those green checks don't cover.

Six of the "Recommended next steps" from the previous version of this doc
are now done (commits `8722946`, `7acf5d2`, `51ba50e`, `188c910`). What's
left is genuinely blocked on things I don't have access to in this
environment (real Postgres credentials) or is a design decision for the
team, not a code fix — flagged clearly below.

---

## ✅ Resolved since the last audit

| # | Issue | Fix | Commit |
|---|---|---|---|
| 1 | **SSRF**: `POST /companies` fetched arbitrary user-supplied URLs with no protection against private IPs / cloud metadata endpoints | Added `app/security.py` (scheme + resolved-IP validation), wired in as an httpx event hook covering every redirect hop, not just the initial request | `7acf5d2` |
| 2 | Stray test artifacts (`live_test.db`, `_init_live_test_db.py`) committed to the repo | Removed | `8722946` |
| 3 | Re-onboarding accumulated stale `Document` rows across repeated runs | `create_company` now deletes old Documents before re-running the pipeline | `51ba50e` |
| 4 | Company URL normalization inconsistent (`example.com` / `https://example.com` / `https://example.com/` could become 3 separate rows) | `scraper._normalize_base` → public `normalize_url`, applied before the dedup lookup | `7acf5d2` |
| 5 | Dead `numpy` dependency (listed, never imported) | Removed from `requirements.txt` | `188c910` |
| 6 | Reddit's public `.json` endpoints confirmed `403 Blocked` in practice — the collector was correctly isolating the failure but never actually returning data | Rewrote on PRAW in OAuth read-only mode (`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`) — same graceful-skip-without-credentials pattern as the other gated collectors | `188c910` |

Each fix has dedicated test coverage (SSRF: 19 new tests including a
redirect-to-cloud-metadata case; re-onboarding cleanup, URL dedup, and the
new Reddit collector all covered too). Full suite: 81/81 passing.

---

## 🔴 Remaining: genuinely blocked (not something I can fix from here)

### Migration `0002_kb_and_companies.py` still untested against real Postgres
All verification (pytest + every live test this session) has used
SQLAlchemy's `Base.metadata.create_all()` against SQLite, which bypasses
Alembic entirely. The Postgres-specific paths in the migration
(`CREATE EXTENSION vector`, `ARRAY(String())`, `Vector(1024)`, the IVFFlat
index) have never actually run. **I don't have Docker or Supabase
credentials in this environment** — this needs `alembic upgrade head` run
against a real Postgres by someone who does, before this is trusted in
production. If you can share a connection string (or run it yourself),
this is the single highest-value remaining check.

### No auth on any endpoint
Still true — `/companies`, `/trend-analyzer/*`, `/knowledge-base/search`
are all open. Phase 1's Authentication & Authorization section is
entirely unbuilt. Fine for local dev; **must** land before any non-local
deployment. This is a build-out, not a quick fix — flagging so it doesn't
get lost, not attempting it as part of this pass.

---

## 🟡 Remaining: needs a product/design decision, not just a fix

- **No distinct status for "scraped fine, but extraction was skipped due
  to missing config."** Onboard a company without `ANTHROPIC_API_KEY` set
  and you get `status: "complete"` with every profile field `null` — no
  signal to the user about *why*. Options: a distinct status (e.g.
  `complete_partial`), or surface a warning even on the graceful-skip path.
  Didn't pick one unilaterally since it changes the status enum contract
  the frontend already depends on.
- **Single-tenant assumption in Trend Matching.** `score_relevance` in
  `trend_analyzer/graph.py` scores trends against "the most recently
  updated `complete` Company" — with 2+ companies onboarded (true right
  now from this session's live testing), trends get scored against
  whichever was touched most recently, silently, no error. Real fix is
  multi-tenancy (a `company_id` on the trend-scoring request, presumably
  tied to an authenticated user) — out of scope until auth exists.

---

## 🟡 External-source fragility (verified live — not code bugs)

- **`pytrends-modern`'s `trending_searches()` 404s** — confirmed live,
  same `hottrends/visualize/internal/data` endpoint Google has moved. No
  fix attempted this pass; would need either a different pytrends method,
  a different library, or accepting Google Trends stays non-functional.
- **YouTube, X/Twitter, Instagram, TikTok** collectors have never been
  tested against live credentials (none are configured anywhere) — only
  verified via mocked tests + the "skip gracefully" path.
- **Reddit** now uses PRAW/OAuth (see above) but has likewise never been
  tested against a real Reddit app registration — only mocked.
- Only **RSS** has been confirmed actually returning real data
  end-to-end, repeatedly, across sessions.

---

## ⚪ Incomplete / deferred features (by design — see TODO.md for full detail)

**Phase 1 — Foundation**
- CI/CD pipeline: not started
- Auth (JWT/OAuth), RBAC, user registration, API key management: not started
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

1. **Run `alembic upgrade head` against a real Postgres** (Supabase or
   local) — the one remaining check I can't do myself here.
2. Decide the "extraction skipped due to missing config" status question
   above, then I (or whoever) can implement it — small change once decided.
3. Start on auth (JWT/OAuth + RBAC) — blocks both the no-auth security gap
   and the single-tenant Trend Matching limitation.
4. If Google Trends data matters, investigate `pytrends-modern` alternatives
   or accept it stays non-functional.
5. Get real credentials for at least one of YouTube/X/Instagram/TikTok/Reddit
   to validate a collector end-to-end beyond the mocked test suite.
