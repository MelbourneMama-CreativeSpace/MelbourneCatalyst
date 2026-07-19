# Known Issues & Incomplete States

Audit compiled after four rounds: the Platform Integration Agent (OAuth
"connect your account" scaffolding for Phase 6), Trend Outputs +
Knowledge Manager (Phase 4 / Phase 3), Content Planner Agent completion
(Phase 5), and this round's Phase 2 Knowledge Base completion — closing
out every non-credential-gated feature identified across this session's
audits, Phase 2 included. Per your steer, credential-based testing (a
real `ANTHROPIC_API_KEY`, real social-platform app credentials, a real
Postgres connection) is explicitly **not** attempted — you're handling
that yourself once implementation work is further along. Everything
below was verified either by automated tests or by live requests against
a throwaway SQLite database + running frontend/backend. Current repo
state: branch `business-analyzer` (all four rounds' work, plus earlier
rounds', not yet committed as of writing this file).

**Backend tests: 296/296 passing (was 258 before this round, 241 before
that, 209 before that, 178 before the OAuth round). Frontend:
lint/typecheck/build all clean.**

---

## ✅ Resolved this round — Phase 2 Knowledge Base completion

Every remaining Phase 2 checklist item, all genuinely buildable without
credentials: Voyage AI embeddings already degrade gracefully to `None`
without a key (same as every prior round's Claude-key handling), and
none of this round's new sources need Claude at all — no LLM call
anywhere in this round's code.

- **Shared ingestion primitive** (`app/agents/knowledge_base/ingestion.py`)
  — `ingest_raw_document()` chunks, embeds, and persists one
  `RawDocument`, deleting any existing rows for that `source_url` first
  so re-running ingestion for the same source replaces rather than
  duplicates. Adopts the `RawDocument` dataclass that existed in
  `schemas.py` but was never actually used anywhere — every new source
  below just builds one and calls this. Same shape as the company
  re-onboarding dedup fixed earlier this session, now generalized.
- **Blog/article indexer** (`app/agents/knowledge_base/blog_indexer.py`)
  — RSS-driven, `POST /documents/blog-index` with a per-request feed URL
  list (deliberately not a global setting like the Trend Analyzer's RSS
  feeds, since a company's own blog feeds are company-specific).
  `feedparser` finds entries, each article page is then scraped and
  extracted the same way the Company Analyzer scrapes a company's own
  site (httpx + trafilatura) — an RSS summary alone is usually too thin
  to be useful for retrieval.
- **Product page tagging** — scraped pages from onboarding whose URL
  path contains `product`/`pricing`/`shop`/`store` now get
  `source_type="product_page"` instead of generic `"website"`.
  Deliberately **not** a new structured-extraction Claude pipeline
  (parsing prices/SKUs) — that would risk generating plausible-looking
  but unverifiable pricing data with no live account to check it
  against, exactly the kind of unverifiable-Claude-output risk this
  project has avoided all session. The honest, low-risk version of
  "specialized" handling is a correct, filterable tag.
- **Business document uploader** — `POST /documents/upload`, PDF/DOCX/TXT/MD
  via new `pypdf`/`python-docx`/`python-multipart` dependencies. A 5MB
  cap (`KB_UPLOAD_MAX_BYTES`) rejects oversized uploads with 413;
  unsupported extensions get a 400, not a silent failure.
- **Document CRUD + dashboard** — `GET/DELETE /documents/{id}`,
  `GET /documents` (paginated, filterable by `source_type`),
  `POST /documents/manual` (a title/content form, no file needed). New
  page `/knowledge-base/[companyId]` — search box (finally wires up
  `searchKnowledgeBase()`, which existed in the API client since an
  earlier round but was never called from any component), upload/
  manual-entry/blog-index forms, a filterable document list with delete.
  Linked from the company page's "Knowledge base" panel via a new
  "Browse knowledge base" button.

**A real SSRF gap found and fixed during live verification, not by
review**: `feedparser.parse(feed_url)` fetches the feed URL itself —
`blog_indexer.py`'s first draft only SSRF-validated each *article* URL
before scraping it, not the *feed* URL before handing it to feedparser.
A `feed_urls` value pointing at an internal/cloud-metadata address would
have reached feedparser's own unguarded HTTP fetch. Caught by manually
testing a cloud-metadata-style address during live verification (the
request hung instead of failing fast, which was the tell) — fixed by
validating `feed_url` with the same `validate_public_url()` check before
`feedparser.parse()` ever runs, plus a dedicated regression test
(`test_index_blog_feeds_rejects_unsafe_feed_url`) that asserts
`feedparser.parse` is never even called for an unsafe URL. Re-verified
live afterward: a private-IP feed URL now rejects instantly instead of
hanging.

**Verified live** against a throwaway SQLite DB: manual entry and a real
generated DOCX both ingested and chunked correctly; an unsupported
`.zip` upload correctly 400s; blog indexing ran against a real public
RSS feed (Hacker News frontpage) and pulled 5 real articles into 68
real chunks; freshness correctly reflected the running total throughout;
re-running blog indexing against the same feed did **not** double the
document count (68 → 68, not 136), confirming the dedup-by-`source_url`
logic works against a real re-run, not just mocked unit tests; document
list/filter/detail/delete all confirmed via curl and, this round, via a
**fully interactive browser walkthrough** — unlike the last two rounds,
this session's `loading.tsx` hydration limitation did not reproduce this
time (459/502 elements hydrated correctly), so the manual-entry form,
source-type filters, and delete button were all exercised through real
clicks/typing, not just `read_page`. 38 new backend tests added this
round, all passing on top of the existing 258.

## ✅ Resolved previous round — Content Planner Agent completion (Phase 5)

The content calendar engine (one Claude call → a flat list of dated
items) already existed; this round closed out every remaining Content
Planner checklist item as an additive extension, no new agent pattern:

- **Configurable plan window** — `POST /content-management/content-plans`
  now accepts an optional `days` field (7/14/30 presets in the UI, "last
  X days" default of 14 unchanged when omitted), covering weekly/
  standard/monthly planning with the same single generator instead of
  three separate agents.
- **Audience-interest tagging** — `audience_interest` on each
  `ContentItem`, Claude-generated, ties an idea back to the company's
  target audience / niche keywords (now included in generation context,
  previously only implicitly present via the company profile summary).
- **Seasonal-event integration** — `seasonal_event` on each item. A
  small fixed-date lookup table (New Year's Day, Valentine's Day,
  Christmas, etc.) computes which awareness/commercial dates fall inside
  the plan's window and offers them as candidates in generation context;
  Claude ties an idea to one only if genuinely relevant. Deliberately
  **excludes movable-date holidays** (Easter, Mother's/Father's Day,
  Black Friday) since the lookup has no year-awareness — a wrong
  computed date would be worse than no suggestion at all.
- **Content preview & approval flow** — new `approval_status`
  (`pending`/`approved`/`rejected`) column on `ContentItem`, same
  "manually advanced, no state-machine enforcement" pattern as
  `Campaign.lifecycle_stage`. New `PATCH /content-management/content-items/{id}`
  updates approval status and/or `suggested_date` in one endpoint —
  the same PATCH also backs rescheduling.
- **Drag-and-drop calendar UI** — `content-plan-view.tsx` rewritten from
  a flat card list into a real month-grid calendar (native HTML5
  drag-and-drop, no new dependency). Dragging an item to a different day
  calls the same PATCH endpoint to reschedule it. Clicking an item opens
  a detail panel with Approve/Reject controls.
- New migration `0009_content_item_planning_columns.py` adds
  `audience_interest`, `seasonal_event`, `approval_status` to the
  existing `content_items` table — no new tables.

**Verified live** against a throwaway SQLite DB seeded with a company,
strategy, and a content plan with 5 items spanning mixed approval
states, themes, and audience/seasonal tags: `GET /content-plans/{id}`
correctly returns every new field; `PATCH /content-items/{id}` correctly
updates approval status, reschedules `suggested_date`, does both at
once, 404s on an unknown item, and 422s on an invalid `approval_status`;
`POST /content-plans` correctly threads a custom `days` value through to
generation (confirmed via the graceful no-key failure path, same as
every other generation endpoint) and defaults correctly when omitted.
All 258 backend tests passed, including 17 new tests added this round
covering the seasonal-event lookup, audience-interest/seasonal-event
parsing and persistence, the `days` override, and the full PATCH
endpoint surface.

### A real, well-characterized tool limitation surfaced this round — not a code defect

Every prior round's browser verification either used pages without a
`loading.tsx` (the company page — fully synchronous SSR, no streaming)
or pages that only needed to be *read*, not clicked (trend-report,
knowledge-audit). This round's calendar needed real interaction (click
to preview, drag-and-drop to reschedule, click Approve/Reject) on a page
that *does* have a `loading.tsx` — and that combination exposed a
genuine limitation in the Claude Browser preview pane, confirmed through
extensive isolation:

- The server-rendered HTML is provably correct — full item data,
  correct dates, correct badges — visible via direct HTML inspection and
  via `read_page`'s accessibility-tree extraction, and independently
  confirmed correct via `curl` against every endpoint.
- But the page never becomes interactive in this tool: React's client
  hydration never completes past the document shell (`document.body
  .innerText` stays empty, no element inside the page's own tree gets a
  `__reactFiber` reference, `getBoundingClientRect()` on any inner
  element returns all-zero, and clicks — both the `computer` tool's
  coordinate-based clicks and a raw DOM `.click()` dispatched directly —
  do nothing).
- Root-caused to the presence of `loading.tsx` (i.e., a streamed
  Suspense boundary): `/companies/[id]` has no `loading.tsx` and
  hydrates perfectly (145/179 elements got real React fibers, clicks
  worked, proven repeatedly this session); every route that *does* have
  one (`content-plan`, `strategy`, and by the same mechanism almost
  certainly `campaign`, `collaboration`, `competitor`, `trend-report`,
  `knowledge-audit`) streams a resolved-but-hidden content chunk plus a
  `$RC("B:0","S:0")` swap script that's present in the HTML but never
  takes effect — even invoking it manually via `window.$RC(...)` had no
  effect, and a from-scratch dev-server restart with a cleared `.next`
  cache, a brand-new browser tab, and a genuine **production build**
  (`next build` + `next start`, zero dev tooling, separate port) all
  reproduced the identical failure. A minimal one-line debug component
  substituted in for the real calendar failed identically, ruling out
  anything about the calendar's own logic.
- **Practical impact**: any future round verifying a `loading.tsx` route
  that needs real click/drag interaction (not just reading rendered
  text) should expect this and lean on `curl` + backend tests for the
  interaction logic, and `read_page`'s accessibility tree (which *does*
  correctly reflect the resolved content) for visual/structural
  confirmation — not `computer` clicks or `getBoundingClientRect()`
  checks, which will report everything as zero-sized and unclickable
  regardless of whether the app is actually fine. This round's approval/
  reschedule logic itself is fully covered by backend tests either way
  (API-level PATCH tests + graph-level persistence tests), so this is a
  verification-method gap, not an unverified feature.
- **Correction from the following round**: the new `/knowledge-base/[companyId]`
  dashboard *also* has a `loading.tsx`, and that round's walkthrough
  hydrated fine on the first try (459/502 elements got real fibers,
  clicks and typing all worked). So this isn't a deterministic per-route
  failure — it's intermittent, possibly timing-dependent on how the
  Suspense boundary's streamed chunk lands relative to when the preview
  tool's automation attaches. Treat a stuck hydration as *possible* on
  any `loading.tsx` route, not *guaranteed* — always check
  `__reactFiber` presence (see the JS snippet used above) before
  concluding a route is unclickable, rather than assuming it from the
  route shape alone.

## ✅ Resolved two rounds ago — Trend Outputs + Knowledge Manager (Phase 4 / Phase 3)

Both reuse the same synchronous one-shot Claude-generation pattern used
throughout this project (Strategy Consultant, Campaign Manager,
Competitor comparison) — no new architectural decisions, same
`status`/`status_error` graceful degradation without a Claude key.

- **`TrendReport`** (`app/agents/trend_analyzer/report_graph.py`) — one
  Claude generation covering a weekly market report, industry insights
  summary, and content-opportunity recommendations in a single call,
  over the top-`TREND_REPORT_MAX_TRENDS` (15) relevance-scored trends
  from the last `period_days` (default 7, configurable per-request).
  `POST /api/v1/trend-analyzer/reports`, `GET .../reports/{id}`,
  `GET .../reports?company_id=`.
- **`KnowledgeAuditReport`** (`app/agents/knowledge_base/audit_graph.py`)
  — one Claude generation producing a coverage summary, identified gaps,
  and recommendations over a sample of up to
  `KNOWLEDGE_AUDIT_MAX_DOCUMENTS` (30) of the company's documents (each
  truncated to 1000 chars). Handles the empty-KB case explicitly rather
  than sending Claude nothing. `POST /api/v1/knowledge-base/audit-reports`,
  `GET .../audit-reports/{id}`, `GET .../audit-reports?company_id=`.
- **Knowledge freshness** (`GET /api/v1/knowledge-base/freshness`) — pure
  computation, no Claude call: `document_count`, `last_ingested_at`,
  `staleness_days` aggregated from the `documents` table. Deliberately
  **not** gated by the usual `company.status == "complete"` readiness
  guard — a company with 0 documents mid-onboarding is meaningful
  information, not an error state.
- New tables `trend_reports`, `knowledge_audit_reports` via migration
  `0008_trend_reports_and_knowledge_audit.py`.
- New frontend: `TrendReports`/`KnowledgePanel` list+generate components
  on the company page, `/trend-report/[id]` and `/knowledge-audit/[id]`
  detail pages (with `error.tsx`/`loading.tsx`).

**Explicitly not attempted, and why**: knowledge graph visualization and
cross-reference linking need a graph UI this project doesn't have and a
linking model that isn't well-defined yet; trend alerts/notifications
need a delivery channel (email/webhook) that doesn't exist. All missing
infrastructure, not missing time — same bar held throughout this
project.

**A routing bug caught by review, before it shipped**: `trends.py`
already had `GET /{trend_id}` registered as a catch-all single-segment
path. Adding `POST /reports` / `GET /reports` *after* it in the file
would have been silently captured by that catch-all (a request to
`/reports` would fail UUID validation trying to parse `"reports"` as
`trend_id`). Fixed by physically registering the new `/reports` routes
before the catch-all, with an explicit warning comment, plus a dedicated
regression test (`test_reports_route_is_not_captured_by_the_trend_id_catch_all`).

**Verified live** against a throwaway SQLite DB seeded with a company,
three trends (varying `discovered_at`/`relevance_score`), and two
documents: freshness returns real counts without any Claude key; report
and audit-report generation both correctly hit the graceful
`status: "failed"` / `status_error: "... check ANTHROPIC_API_KEY ..."`
path (no key set in this environment); the `/reports` vs `/{trend_id}`
routing fix confirmed working both ways; browser walkthrough confirmed
both "Generate ..." buttons trigger the POST, refresh the list, and the
new report appears at the top — and both detail pages render the
failure state with the correct badges. All 241 backend tests passed on
the first full run this round — no bugs found in the new code itself,
only the routing risk above (caught proactively, never actually
regressed).

## ✅ Resolved three rounds ago — Platform Integration Agent (Phase 6)

Genuinely new architectural territory, not another application of an
already-proven pattern — this is the first real external OAuth flow and
the first encrypted secrets anywhere in this codebase.

- **Generic OAuth2 authorization-code flow**, one implementation shared
  across all 6 platform surfaces (Instagram, Facebook, X, LinkedIn,
  TikTok, YouTube — Instagram and Facebook share one Meta app, same as
  their real-world relationship): `build_authorize_url()` /
  `exchange_code_for_token()` in
  `app/agents/social_media_analyzer/oauth_flow.py`, parameterized per
  platform via a config table in `oauth_providers.py`. X's flow
  additionally does PKCE (code_challenge/verifier), since X requires it
  even for confidential clients.
- **No session system exists** (auth is still deferred — see below), so
  the OAuth `state` param carries everything the callback needs
  (company_id, platform, nonce, PKCE verifier), HMAC-signed and
  timestamped via `app/security/oauth_state.py` so it can't be forged or
  replayed after 10 minutes.
- **Tokens are encrypted at rest** — `app/security/token_encryption.py`,
  Fernet symmetric encryption keyed by `TOKEN_ENCRYPTION_KEY`. This is a
  materially different risk than everything else this app stores: a
  leaked row here is a real, usable third-party credential, not just
  business profile data.
- Five endpoints under `/social-media-analyzer/*`: list connections
  (always returns all 6 platforms, synthesizing `"disconnected"`
  placeholders for ones never attempted, so the frontend has a stable
  list to render), authorize (redirects to the real platform, or a clear
  409 if that platform's app isn't configured), callback (exchanges the
  code, persists the connection, redirects back to the frontend),
  disconnect, and a metrics endpoint that's schema-complete but always
  returns an empty list (see below).
- New `PlatformConnections` component on the company page — one row per
  platform, "Connect" (plain `<a href>`, not a fetch call — OAuth needs a
  real browser navigation) or "Connected as X / Disconnect".
- New tables `platform_connections`, `platform_metric_snapshots` via
  migration `0007_social_media_analyzer.py`.

**Explicit scope decision, confirmed with you before starting**:
Performance Tracking, Social Analytics, and Channel Intelligence (Phase
6's other three sub-agents) get **schema and UI shells only this
round** — `platform_metric_snapshots` exists but nothing writes to it.
Their actual per-platform metrics-parsing logic is deliberately not
implemented, since it can't be verified without a real connected account
and guessing at API response shapes from training knowledge is exactly
the kind of unverifiable risk this project has avoided elsewhere.

**Verified live, without any real platform credentials**: `GET
/connections?company_id=` correctly returns all 6 platforms as
`disconnected`; `GET /connections/instagram/authorize` correctly 409s
with "not configured" when unset. Then, with a *fake* `META_APP_CLIENT_ID`
+ a real generated `TOKEN_ENCRYPTION_KEY` temporarily set (removed
after), the same endpoint produced a **fully correct, real** Meta OAuth
authorize URL — right host, right scopes, a validly-signed state
param — confirming the URL-construction logic works, even though the
fake client ID means Meta itself would reject it. The full click-driven
browser redirect to an external host couldn't be verified end-to-end —
the preview browser sandbox blocks cross-origin navigation to a
different port/host — but the exact redirect URL was independently
confirmed correct via a direct request.

### A real bug caught by a stale-attribute check, not by review

`disconnect()` committed changes to a `PlatformConnection` row, then
immediately called `PlatformConnectionOut.model_validate()` on the same
in-memory object — which crashed with `MissingGreenlet` on `updated_at`.
That column has `onupdate=func.now()`, so its real post-commit value is
unknown to the ORM object until refreshed, *regardless* of this app's
`expire_on_commit=False` session setting (that setting only covers
plain attributes, not server-computed ones — SQLAlchemy expires
those specifically at flush time no matter what). Content Management's
`update_campaign_lifecycle` already had the right fix
(`await session.refresh(obj)` before serializing) — I just hadn't
applied the same fix here. One line, caught by the test suite
immediately.

### Auth is a harder blocker now than it was

Every prior round's `KNOWN_ISSUES.md` noted no-auth as a deferred choice
covering business-profile-type data. That's no longer the full picture:
**this app can now store real third-party OAuth tokens against an
unauthenticated `Company` row.** Anyone who can reach the API can
trigger a connect flow for any company and, once a real platform app is
registered, the resulting access token would be stored against whatever
`company_id` they supplied — there's nothing verifying the caller
actually represents that business. This doesn't block using the feature
locally, and no fix is applied here (still your call, per your earlier
explicit choice) — but it's the reason auth should move from "nice to
have before deployment" to "needed before you register any real
platform app and actually test this."

## ✅ Resolved earlier rounds — Competitor Research Agent

`POST /competitor-research/competitors` onboards a competitor by URL,
reusing Company Analyzer's scraper/extractor directly — verified live
against a real website (`example.com`). `POST .../comparison` generates
a Company-vs-Competitor analysis once both profiles are ready. Not
attempted: social presence tracking, customer engagement monitoring
(need live platform data). New table `competitors` via
`0006_competitor_research.py`.

## ✅ Resolved earlier rounds — bug fixes + hardening (carried forward for context)

Cross-company data leaks fixed everywhere (every cross-reference across
strategy/content-plan/campaign/collaboration/competitor now validates it
belongs to the same company), a malformed-Claude-item crash fixed (full
item construction wrapped in `try/except`, reused in every
list-generating agent since), a company-readiness guard
(`_get_ready_company_or_error`, 409s instead of generating from an empty
profile), `error.tsx`/`loading.tsx` boundaries on every detail route, a
"past X" history section, a batch trend-lookup endpoint. Plus the
original hardening rounds: SSRF protection, stray test artifacts,
document accumulation on re-onboarding, URL normalization, dead `numpy`
dependency, Reddit's PRAW/OAuth rewrite, `complete_no_profile` status,
Google Trends `related_queries()` rewrite.

---

## 🔴 Remaining: deferred by your explicit choice, not blocked

### No auth on any endpoint
Now materially more urgent — see the callout above. Recommendation
unchanged: Supabase Auth — also fixes the single-tenant Trend Matching
limitation below.

### Migrations `0007`–`0009` (and `0002`–`0006`) still untested against real Postgres
Now nine migrations deep, all verified only against SQLite via
`Base.metadata.create_all()`, which bypasses Alembic entirely.

### No agent's Claude call has run against a real `ANTHROPIC_API_KEY`
Same caveat as prior rounds. Separately: no platform's OAuth app has
been registered anywhere, so no `PlatformConnection` has ever gone
through a real authorize → consent → callback → token-exchange cycle —
only the URL-construction half is live-verified (see above); the token
exchange itself is only verified via mocked tests.

---

## 🟡 Remaining: needs a product/design decision, not just a fix

- **Single-tenant assumption in Trend Matching** (unchanged) —
  `score_relevance` scores trends against "the most recently updated
  `complete` Company." Every agent that reads trends inherits this.
  Real fix is multi-tenancy tied to auth.
- **Connected-account display name/ID resolution isn't implemented.**
  `TokenResult.external_account_id`/`external_account_name` are always
  `None` after a real connection completes — resolving them needs a
  platform-specific "who am I" follow-up call (Meta's `/me`, Google's
  userinfo endpoint, etc.), deliberately left out this round for the
  same reason as the metrics-fetching logic: unverifiable without a real
  connected account. The connection still works correctly without it,
  just shows "Connected" instead of "Connected as @yourhandle" until a
  follow-up round adds this.

---

## 🟡 External-source fragility (verified live in prior rounds — not code bugs, unchanged, credential-gated)

- **YouTube, X/Twitter, Instagram, TikTok** trend collectors have never
  been tested against live credentials (distinct from this round's
  OAuth work — those are separate, static, app-level API keys, not the
  new per-account OAuth connections).
- **Reddit** uses PRAW/OAuth but has likewise never been tested against
  a real Reddit app registration — only mocked.
- **RSS and Google Trends** are the only two trend sources confirmed
  returning real data end-to-end, live. The Company Analyzer/Competitor
  Research *website scraper* is also confirmed live (`example.com`).

---

## ⚪ Incomplete / deferred features (by design — see TODO.md for full detail)

Every agent with a genuine non-credential slice is now built and
complete: all of **Phase 2** (Knowledge Base, as of this round), Phase 5
(including the Content Planner Agent's full checklist), Competitor
Research in Phase 3 (plus Knowledge Manager's freshness scoring + audit
reports), Phase 4's Trend Outputs, and Platform Integration in Phase 6.
What remains is all credential-gated or missing-infrastructure:

- **Phase 6** (Performance Tracking, Social Analytics, Channel
  Intelligence) needs a real connected account to build against
  honestly, not just more time.
- **Phase 2/3 Knowledge Manager remainder** (cross-reference linking,
  knowledge graph visualization) needs a linking model and graph UI that
  don't exist yet. Re-indexing is now idempotent for every source
  (re-running any ingestion replaces rather than duplicates), but
  content-hash-based *partial* diffing — skipping a source entirely when
  nothing changed, instead of always re-embedding it — remains a stretch
  goal, not attempted.
- **Phase 2 social media profile importer** — same OAuth/API-tier
  access this app already has for Performance Tracking (Phase 6), still
  needs a real connected account before it can pull profile content in.
- **Phase 4 remainder** (daily trending-topics digest, campaign-history
  comparison, competitor-activity correlation, trend alerts) needs
  either a delivery channel or data from Phase 5/Phase 6 that isn't
  populated with live results yet.

See `TODO.md` for the full phase-by-phase checklist.

---

## Priority list for next round

1. **Register at least one platform's developer app** (Google Cloud for
   YouTube is usually the fastest/least gated of the five) and drop its
   Client ID/Secret + a generated `TOKEN_ENCRYPTION_KEY` into `.env` —
   this unblocks a real end-to-end connection test, which in turn
   unblocks starting Performance Tracking for real (something to verify
   the metrics-parsing logic against, instead of guessing).
2. All non-credential-gated agent work identified so far is now built,
   Phase 2's Knowledge Base included. Any further backend feature work
   is either credential-gated (Phase 6 metrics, Phase 2's social profile
   importer) or needs a product/design decision first (graph UI, linking
   model, notification delivery channel — see the 🟡 sections above).
3. When ready for the rest of credential-based testing: a real
   `ANTHROPIC_API_KEY` (biggest single unknown — no agent's actual
   output quality has been seen yet, including every generation added
   across the last three rounds), a Postgres connection string for
   `alembic upgrade head` (9 migrations deep now).
4. Auth (Supabase Auth recommended) — worth moving up your own priority
   list given the OAuth-token exposure noted in the previous round,
   whenever you're ready to take it on.
