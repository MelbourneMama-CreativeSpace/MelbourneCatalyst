# Known Issues & Incomplete States

Audit compiled after nine rounds. This round replaced Platform
Integration's OAuth handling with Composio, per your explicit steer —
this app no longer does raw OAuth itself or stores tokens, and Platform
Integration got a real dedicated `/integrations/[companyId]` page
instead of being buried on the company page. Per your steer,
credential-based testing (a real `ANTHROPIC_API_KEY`, a real
`COMPOSIO_API_KEY` + registered platform apps, a real Postgres
connection) is explicitly **not** attempted — you're handling that
yourself once implementation work is further along. Everything below
was verified either by automated tests or by live requests against a
throwaway SQLite database + running frontend/backend. Current repo
state: branch `business-analyzer` (all nine rounds' work, plus earlier
rounds', not yet committed as of writing this file).

**Backend tests: 331/331 passing (was 338 before this round — net
fewer despite new coverage, since this round deleted the raw-OAuth
security submodules and their tests outright rather than adapting them;
was 320 before that, 315 before that, 305 before that, 296 before that,
258 before that, 241 before that, 209 before that, 178 before the OAuth
round). Frontend: lint/typecheck/build all clean.**

---

## ✅ Resolved this round — Platform Integration migrated to Composio + dedicated integrations page

You asked specifically to use Composio instead of this app doing raw
OAuth — this is a full replacement, not an addition alongside the old
flow. See the round eight-rounds-back entry below for what this
replaces; that entry is left as an accurate historical record rather
than rewritten.

- **Verified the real SDK before writing any code.** Docs for
  `composio`/`composio-client` described a newer/unreleased SDK
  generation (raw `client_id`/`client_secret` in `auth_configs.create()`)
  that doesn't match what's actually on PyPI. Rather than guess, I
  installed the real released package (`composio-client==1.42.0`) into
  an isolated scratch venv and introspected its actual type definitions.
  Confirmed: registering a platform's own OAuth app credentials happens
  once, by hand, in Composio's dashboard (creating a `use_custom_auth`
  config there) — not through this SDK. This app only ever holds the
  resulting auth config id.
- **Dependency choice**: used `composio-client` (the low-level REST
  resource client) rather than the higher-level `composio` package —
  confirmed via a second isolated-venv install that the latter forces a
  `pydantic` upgrade past this app's pinned `2.11.3` (it depends on
  `openai`/`pysher`, unrelated to anything this app needs) while
  `composio-client` alone installs clean against the existing pin.
  Verified by actually installing it into the main project venv, not
  just asserting compatibility.
- **`PlatformConnection` no longer stores tokens at all** — the
  `access_token_encrypted`/`refresh_token_encrypted`/`token_expires_at`
  columns are gone (migration `0015`), replaced by
  `composio_connected_account_id`, a reference to Composio's own token
  custody. `app/security/token_encryption.py` and
  `app/security/oauth_state.py` are deleted outright, along with their
  tests — Composio's hosted OAuth flow makes both unnecessary (no tokens
  to encrypt; no local `state` param to sign, since Composio's own
  hosted callback handles the platform redirect, not this app).
- **The callback route is gone.** Composio's hosted endpoint is now the
  registered OAuth redirect target on each platform's app, not this
  backend — after consent, Composio redirects the browser straight to
  `/integrations/{company_id}`. `GET /connections` lazily refreshes any
  connection still in a `"pending"` state (via
  `connected_accounts.retrieve`) so status is current by the time the
  user lands back on that page, rather than needing a webhook or a
  background poller.
- **New dedicated `/integrations/[companyId]` page** (`IntegrationsView`)
  replacing the old `PlatformConnections` panel that was buried inside
  the company page's collapsed "Other modules" accordion — per-platform
  cards with live status, Connect/Disconnect, and an expandable
  per-connection analytics section that honestly shows "No metrics
  yet" (real behavior — the metrics endpoint still returns nothing,
  unchanged from before) rather than fabricating anything. The company
  page now links out to it directly instead of embedding it.
- New `ConnectionStatus` value `"pending"` (frontend + backend) for the
  window between initiating a connection and Composio confirming it —
  previously connections only had a binary connected/disconnected feel.

**Verified live** against a throwaway SQLite DB seeded with a connected
Instagram row and a pending LinkedIn row (fake Composio ids, no real
`COMPOSIO_API_KEY` in this environment): `GET /connections` correctly
attempted a real status check against Composio for the pending
LinkedIn row, which correctly failed (no valid key) and mapped to
`"error"` — proving the graceful-degradation path executes for real,
live, not just in a mocked test. `GET
.../instagram/authorize` correctly 409'd with the new "set
COMPOSIO_API_KEY and its auth config id" message. `DELETE` on the
connected row correctly attempted a real Composio disconnect call
(which failed the same way, swallowed as designed) and still cleared
the local row. Browser walkthrough confirmed the new `/integrations`
page renders all 6 platforms with correct live statuses, and the
company page's link and updated "Other modules" copy (no longer
mentioning "connected platforms," since that's not buried anymore).
21 new/changed backend tests this round; net test count went down
because two whole test files (`test_oauth_state.py`,
`test_token_encryption.py`) were deleted along with the modules they
tested.

**What's still unverified, same caveat as always**: no real
`COMPOSIO_API_KEY` or registered platform OAuth apps exist in this
environment, so the actual end-to-end connect flow — Composio's
hosted authorize page, a platform's real consent screen, the redirect
back — has not been seen firsthand. Everything above is verified as far
as this environment allows: real SDK signatures, real (if
credential-less) API calls proving the failure paths work, and the full
UI. The one thing only a real `COMPOSIO_API_KEY` can confirm is whether
Composio's dashboard-created auth config actually round-trips to a
working connection for each of the 6 platforms.

## ✅ Resolved previous round — Content Studio: real drafts, one framing, honest numbers

Directly answers the founder's four build requirements from
`priority_todolist.md` (P0–P3); see that file for the full checklist.

- **The MVP bar is now cleared** — `ContentItem` gained a `draft_copy`
  field (migration `0013`): finished, platform-appropriate,
  ready-to-publish caption text, not a brief. The Claude tool prompt in
  `content_planner.py` was rewritten from "specific enough to brief a
  writer" to "someone should be able to copy this verbatim and post it,"
  mirroring the pattern already proven correct in
  `collaboration.py`'s `outreach_template` field. A new `POST
  /content-items/{id}/regenerate-draft` endpoint re-drafts a single item
  without regenerating the whole calendar. The calendar detail panel now
  shows the draft prominently with copy-to-clipboard and a regenerate
  button, ahead of the underlying brief.
- **Named the one recurring task**: drafting the actual caption copy for
  every slot in the weekly calendar — the highest-frequency, most
  mechanical, least-loved step in a 28-post cycle, per the audit's
  recommendation. **This is still your call to confirm with the
  founder**, not something a build round can settle on its own — the
  copy changes below assume this answer.
- **Reframed the product around that task**: the homepage no longer
  pitches four modules with a marketing hero — it leads with "This
  Week's Captions, Drafted" and two buttons ("Open Content Studio," "Add
  a client"). The strategy page's CTA is now "Draft this week's
  captions" instead of "Generate content plan." The company page
  collapses competitor research, platform connections, trend reports,
  and the knowledge base behind an "Other modules (in development)"
  disclosure — routes still work, just not front and center.
- **Removed fabricated numbers from the product itself, not just agent
  outputs** — the landing page previously claimed "100+ Data Sources,"
  "<1s Response Time," "24/7 Monitoring," none of which were real. The
  Features section previously listed generic "Predictive Analytics" /
  "Global Coverage" claims nothing in the codebase does. Both replaced
  with an honest description of Content Studio's five real agents,
  including stating plainly that Analytics isn't built yet.
- **Basic user identity** — `approved_by` (free-text, not real auth)
  added to `Strategy` and `ContentItem`, set from a name field
  remembered in `localStorage` so a small team can see who approved or
  rejected what without a full auth system.
- **Multi-tenant trend scoring, partially fixed** — new
  `CompanyTrendRelevance` table (migration `0014`) scores every new
  trend against *every* complete company, not just whichever one was
  "most recently updated." The Content Planner's trend context now
  reads from it. Strategy Consultant, Campaign Manager, Brand
  Collaboration, Trend Reports, and the `/trends`/`/recommended`
  endpoints still read the legacy single-tenant score — see the 🟡
  section below for why this wasn't done everywhere in one pass.

**Verified live** against a throwaway SQLite DB seeded with two
companies (proving the multi-tenant trend fix), a content plan with a
seeded `draft_copy`, and a strategy: `GET` on the content plan returned
`draft_copy` correctly; `PATCH .../content-items/{id}` with
`approved_by` set it correctly and left it `null` on a pure reschedule;
`POST .../regenerate-draft` correctly 502'd (no `ANTHROPIC_API_KEY` in
this environment — same caveat as every prior round's generation work)
and 404'd for an unknown item; `PATCH .../strategies/{id}/approval` set
`approved_by` correctly. Browser walkthrough (via `read_page` — the
`loading.tsx` hydration quirk documented below reproduced again this
round on `/content-plan/[id]` and `/strategy/[id]`) confirmed the
homepage's new copy, the company page's collapsed "Other modules"
section, and the strategy page showing "Approved by Priya" plus the
reframed "Draft this week's captions" button. 18 new backend tests
added this round (338/338 total).

**Caveat carried over explicitly**: this environment still has no real
`ANTHROPIC_API_KEY`, so the actual quality of Claude's generated
`draft_copy` — whether it genuinely reads as publishable copy rather
than something that merely satisfies the schema — has not been seen
firsthand. That's the one thing worth checking yourself first once a
key is configured, before treating this as fully proven end-to-end.

## ✅ Resolved two rounds ago — Strategy approval workflow (Phase 5 / Phase 6 audit)

Closes the last genuinely buildable Phase 5 item. Phase 6 was
re-audited in full and has **zero** buildable items left: the OAuth
*connection* flow (built five rounds ago) is the only piece of Platform
Integration that doesn't need a real connected social account, and every
remaining Phase 6 item — all six platform data integrations, all of
Performance Tracking, all of Social Analytics, all of Channel
Intelligence — is downstream of data this environment can't produce
without one. This specifically includes "platform-specific trend
detector," which is *not* redundant with Phase 4's trend collection
(that's public web trends; this is trends on the company's own connected
channel) but is equally credential-gated.

- **Strategy approval workflow** — `Strategy` had a generation `status`
  but, unlike `ContentItem`/`Campaign`, no manual review lifecycle.
  Added `approval_status` (pending/approved/rejected, migration `0012`),
  a `PATCH /content-management/strategies/{id}/approval` endpoint (same
  get-or-404 → mutate → commit → refresh shape as every other
  approval/lifecycle PATCH in this codebase), and Approve/Reject buttons
  + a status badge on the strategy page, mirroring `ContentItemDetail`'s
  pattern in `content-plan-view.tsx` exactly (same badge/border style
  constants, same disabled-when-already-that-status behavior).
- Every other Phase 5 item stays deferred for the same reason as before:
  Campaign's real-time performance tracker/progress dashboard/A-B
  testing/reports generator, Brand Collaboration's influencer discovery
  engine + ROI predictor, and the entire 7-item Analytics Agent all need
  real campaign or engagement data from a connected platform that
  doesn't exist in this environment.

**Verified live** against a throwaway SQLite DB seeded with a completed
company + a completed strategy: `PATCH .../approval` correctly
transitioned `pending → approved → rejected → pending` (200s, correct
body each time), rejected an invalid enum value (422), and 404'd on an
unknown strategy id. Browser walkthrough via `read_page`'s accessibility
tree (not `computer` clicks — see the `loading.tsx` hydration note
below, which reproduced again this round on `/strategy/[id]`) confirmed
the rendered page shows the "pending" approval badge alongside the
"complete" status badge and both Approve/Reject buttons in their correct
enabled state. 5 new backend tests added this round (320/320 total).

## ✅ Resolved three rounds ago — Phase 4 completion (Trend Matching + Trend Outputs)

Closes the last two genuinely buildable Trend Matching items and the
last Trend Outputs item that didn't need a real delivery channel. Trend
alerts/notifications and all of Performance Discovery stay deferred —
see below.

- **Campaign history comparison + competitor activity correlation** —
  rather than a new deterministic scoring subsystem bolted onto `Trend`
  (which risked producing raw similarity numbers with no actionable
  meaning), both are now genuinely new content *inside* the existing
  weekly `TrendReport` generation: `_gather_context_node` in
  `report_graph.py` now also pulls the company's recent campaigns
  (objective text) and competitors (profile summary) into context, and
  the `generate_trend_report` tool gained two fields —
  `campaign_alignment_notes` and `competitor_relevance_notes` — so
  Claude explicitly reasons about whether the period's trends echo a
  past campaign or a competitor's positioning, grounded in real rows,
  not invented. Both were correctly blocked by "needs Phase 3/5 first"
  until those phases actually landed a few rounds ago — this round just
  wires up the now-available data.
- **Trend recommendation engine** — `GET /api/v1/trend-analyzer/recommended`
  formalizes the dashboard's manual `min_relevance` filter into an
  opinionated, deterministic shortlist (relevance above
  `TREND_RECOMMENDATION_MIN_RELEVANCE`, discovered within
  `TREND_RECOMMENDATION_MAX_AGE_DAYS`) — no Claude call, pure filter
  over the `relevance_score` the collection graph already computes. A
  new "Recommended" toggle on `/trends` surfaces it, disabling the other
  filters while active since the endpoint doesn't accept them.
- **Daily trending topics feed** — `run_scheduled_daily_reports`, a new
  APScheduler job (`TREND_DAILY_REPORT_INTERVAL_HOURS`, default 24)
  mirroring the Phase 2/3 KB re-index job's shape exactly: loop over
  every `status == "complete"` company, generate a `period_days=1`
  `TrendReport`, isolate per-company failures. Same "no delivery channel
  needed" resolution as that job — the existing trend-reports list *is*
  the delivery surface, so this doesn't need email/webhook
  infrastructure the way real alerts/notifications would.
- **LinkedIn trending topics stays deliberately unbuilt** — the TODO
  item's own wording ("would require scraping") is the tell: LinkedIn
  has no public trends API outside approved Marketing Partners, so the
  only path is scraping a login-walled, aggressively anti-bot site. That's
  a ToS/legal risk this project has avoided everywhere else (the
  Company Analyzer's scraper only ever touches a company's *own* public
  site, with SSRF guards and a real User-Agent) — not attempted, and
  shouldn't be without you explicitly asking for it.

**Verified live** against a throwaway SQLite DB seeded with a company, a
completed Campaign (with an objective), a completed Competitor (with a
unique value prop), and three trends spanning the recommendation
boundary (high-relevance + fresh, low-relevance, high-relevance + stale):
`GET /recommended` correctly returned only the one trend meeting both
bars; `POST /reports` correctly hit the graceful `status: "failed"` path
with both new fields present as `null` (no `ANTHROPIC_API_KEY` in this
environment); `run_scheduled_daily_reports()` was invoked directly and
confirmed it created a real `period_days=1` report for the seeded
company without raising. Browser walkthrough confirmed the `/trends`
"Recommended" view renders the correct single-item shortlist with the
right copy — via direct URL navigation to `?recommended=1` rather than
a click-through, since this session's known `loading.tsx` hydration
quirk (documented two rounds ago) reproduced on `/trends` this time;
since the toggle is just a `router.push` to that exact URL, this is an
equivalent verification of the same code path, not a workaround around
untested code. 10 new backend tests added this round (315/315 total).

## ✅ Resolved four rounds ago — Phase 3 completion (Business Analyst + Knowledge Manager)

Closes out the last two genuinely buildable Phase 3 items. The other two
(Competitor Research's social presence tracker and customer engagement
monitor) stay deferred — both need live follower/engagement/review data
from a connected platform, same credential blocker as Phase 6's
Performance Tracking, not a code gap.

- **Products & services cataloging** — `products_and_services` added to
  the same `extract_company_profile` Claude tool call that already
  produces `niche_keywords` (no second API call). New `Company` column
  (migration `0010`), new `CompanyOut` field, a "Products & services"
  badge section on the company page right below niche keywords.
- **Automated knowledge indexing** — a new APScheduler job,
  `run_scheduled_reindex` (`KB_REINDEX_INTERVAL_HOURS`, default 24),
  registered in `main.py`'s `lifespan` alongside the existing
  `trend_collection` job with the same `coalesce=True`/`max_instances=1`
  guards. Loops over every `status == "complete"` Company and re-scrapes
  its own site via the same `discover_and_scrape` the onboarding
  pipeline uses — this is genuinely new: no prior job in this codebase
  loops over *all* companies (the Trend Analyzer's relevance-scoring is
  explicitly single-tenant, `.limit(1)`).
- **Incremental update pipeline** — `ingest_raw_document_if_changed()`
  in `ingestion.py`: computes a sha256 hash of the freshly-scraped page
  content, compares it against the hash tagged in the previously-stored
  `Document.raw_metadata` for that `source_url`, and skips the embedding
  call (plus the delete+reinsert) entirely when nothing changed. A
  source with no prior recorded hash — e.g. a document ingested by the
  original onboarding pipeline, before this feature existed — is treated
  as "changed" rather than silently trusted, so the worst case is one
  redundant re-embed, not a silently-stale KB entry.
- `classify_source_type` (product-page tagging, shipped last round)
  moved from `company_analyzer/graph.py` to `company_analyzer/scraper.py`
  as a public function, so the new re-index job can reuse it without
  duplicating the classification logic or creating a circular import.

**Verified live**: `reindex_company()` run directly against a real,
external site (`https://example.com`, no mocking) — first run scraped
and ingested 1 page (`pages_changed: 1`); running it again immediately
after correctly reported `pages_changed: 0` with zero new embedding
calls, confirming the content-hash skip works against a real re-scrape,
not just a mocked unit test. `GET /companies/{id}` confirmed
`products_and_services` round-trips through the API; the company page's
new "Products & services" section confirmed rendering via a live browser
walkthrough. 9 new backend tests added this round (305/305 total),
including a dedicated failure-isolation test proving one company's
scrape error doesn't abort a scheduled batch covering the rest.

## ✅ Resolved five rounds ago — Phase 2 Knowledge Base completion

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

## ✅ Resolved six rounds ago — Content Planner Agent completion (Phase 5)

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

## ✅ Resolved seven rounds ago — Trend Outputs + Knowledge Manager (Phase 4 / Phase 3)

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

## ✅ Resolved eight rounds ago — Platform Integration Agent (Phase 6)

> **Superseded this round.** Everything below describing raw OAuth,
> `token_encryption.py`, `oauth_state.py`, and the `PlatformConnections`
> panel is an accurate record of what was true at the time — none of it
> is how the app works anymore. See "Resolved this round" at the top of
> this file for the Composio-based replacement. Left as-is rather than
> rewritten, so this stays an honest history of what actually happened.

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
Still true, and now reaches further than it used to: anyone who can
reach the API can trigger a connect *or disconnect* flow for any
`company_id`, and the new `/integrations/[companyId]` page makes that
surface easier to find, not harder — it's a real page now, not a
collapsed accordion. Composio custodying tokens instead of this app
means a leaked DB row can no longer hand someone a usable third-party
credential directly, which is a real improvement, but the "anyone can
act on any company's connections" gap is unchanged. Recommendation
unchanged: Supabase Auth — also fixes the single-tenant Trend Matching
limitation below.

### Migrations `0007`–`0015` (and `0002`–`0006`) still untested against real Postgres
Now fifteen migrations deep, all verified only against SQLite via
`Base.metadata.create_all()`, which bypasses Alembic entirely — and,
this round, confirmed *why* that's the only option here: migration
`0001` uses a Postgres-specific `JSONB` type that Alembic can't even
compile against SQLite, so `alembic upgrade head` has never been
runnable in this environment at all, for any round, not just this one.

### No agent's Claude call has run against a real `ANTHROPIC_API_KEY`
Same caveat as prior rounds. Separately: no Composio account or
registered platform OAuth app exists in this environment, so no
`PlatformConnection` has ever gone through a real connect → platform
consent → Composio callback cycle — only the failure/graceful-degradation
paths are live-verified (see above); a successful connection is only
verified via mocked tests.

---

## 🟡 Remaining: needs a product/design decision, not just a fix

- **Single-tenant assumption in Trend Matching — partially fixed two
  rounds ago, unchanged since.** `score_relevance` still writes a single global
  `Trend.relevance_score` against "the most recently updated `complete`
  Company," but a new `CompanyTrendRelevance` table (migration `0014`)
  now additionally scores every new trend against *every* complete
  company, and the Content Planner's trend context reads from it in
  preference to the legacy global score. Strategy Consultant, Campaign
  Manager, Brand Collaboration, Trend Reports, and the `/trends` +
  `/recommended` endpoints still read the legacy single-tenant score —
  switching all of those over in one pass wasn't attempted, since doing
  it without a real second-client scenario to verify against risked
  introducing subtle relevance-ranking regressions across every
  generation agent at once. Real full fix is still multi-tenancy tied to
  auth; this round's change makes the Content Planner correct in the
  meantime.
- **Knowledge Base cross-reference linking has no defined linking
  model.** Deliberately not attempted this round or any prior round —
  "link documents/entities" doesn't yet specify *what* should link to
  *what* (documents to competitors? to trends? duplicate/near-duplicate
  detection across sources?) or what the linking should be used for
  (a related-documents sidebar? something graph-shaped?). Inventing an
  answer unprompted risks building the wrong thing — this is a genuine
  "tell me what you want" gap, not a missing-code gap. Knowledge graph
  visualization is blocked on this same decision, since there'd be no
  meaningful edges to draw without it.
- **Connected-account display name/ID resolution still isn't
  implemented — now for a different reason.** `PlatformConnection`'s
  `external_account_id`/`external_account_name` columns still exist,
  but the new Composio-based `authorize` endpoint never populates them
  (the old code path that tried to, via a platform-specific "who am I"
  call, was deleted along with the rest of raw OAuth). Composio's
  `connected_accounts.retrieve()` response has a `data` field that
  likely carries this — unconfirmed, since introspecting a Pydantic
  type doesn't tell you what a real API actually returns in that
  unstructured dict, and there's no real connected account in this
  environment to check against. The connection still works correctly
  without it, just shows "connected" instead of "Connected as
  @yourhandle" until a follow-up round adds this, once there's a real
  connection to inspect the `data` field of.

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
complete: **all of Phase 2** (Knowledge Base), **all of Phase 3**
(Business Analyst + Competitor Research's non-credential items +
Knowledge Manager), **all of Phase 4** (Trend Discovery's non-scraping
sources, all of Trend Matching, and Trend Outputs' non-delivery-channel
items), **all of Phase 5** (Content Planner Agent's full checklist plus
the Strategy approval workflow — every remaining Phase 5 item is
credential-gated, see below), and Platform Integration in Phase 6 (now
Composio-based — see "Resolved this round" at the top).
What remains is all credential-gated, ToS/legal-risk, or
missing-infrastructure:

- **Phase 6** (everything beyond Platform Integration's OAuth connection
  flow — all 6 data integrations, Performance Tracking, Social
  Analytics, Channel Intelligence) needs a real connected account to
  build against honestly, not just more time. Re-audited this round in
  full: zero buildable items remain, including "platform-specific trend
  detector" (not redundant with Phase 4's trend collection, but equally
  credential-gated).
- **Phase 5 remainder** (Campaign's real-time performance tracker,
  progress dashboard, A/B testing, reports generator; Brand
  Collaboration's influencer discovery engine + ROI predictor; the
  entire Analytics Agent) needs real campaign/engagement data from a
  connected platform — same blocker as Phase 6.
- **Phase 3 Competitor Research remainder** (social presence tracker,
  customer engagement monitor) needs live follower/engagement/review
  data from a connected platform — same blocker as Phase 6.
- **Phase 4 Performance Discovery** (all 6 items — content performance
  analyzer, engagement pattern recognition, format effectiveness
  scoring, success/failure pattern learning, performance insights
  dashboard, historical performance reports) needs real published-content
  performance data from a connected platform — same blocker as Phase 6,
  never attempted for the same reason.
- **Phase 4 LinkedIn trending topics** — no public API exists; the only
  path is scraping a login-walled, anti-bot-hardened site, which is a
  ToS/legal risk this project has avoided everywhere else. Not a
  credential gate exactly, but the same "won't build without you
  explicitly asking for it" category.
- **Phase 4 trend alerts & notifications** — needs a real delivery
  channel (email/webhook) and the credentials that come with it (SMTP,
  a notification service). Distinct from the daily trend report job
  (now done), whose "delivery" is just the existing UI.
- **Phase 2/3 Knowledge Manager remainder** (cross-reference linking,
  knowledge graph visualization) needs a linking model that hasn't been
  defined yet (see the 🟡 section above) and a graph UI that doesn't
  exist.
- **Phase 2 social media profile importer** — same OAuth/API-tier
  access this app already has for Performance Tracking (Phase 6), still
  needs a real connected account before it can pull profile content in.

See `TODO.md` for the full phase-by-phase checklist.

---

## Priority list for next round

**The phase-completeness framing below is still on hold** — the active
priority has been `priority_todolist.md` and, this round, Platform
Integration's Composio migration, both by your explicit request rather
than the next phase in sequence. In order:

1. **Set up Composio for real**: create a `COMPOSIO_API_KEY`, then in
   Composio's dashboard create one `use_custom_auth` config per platform
   you want live (Instagram, Facebook, X, LinkedIn, TikTok, YouTube),
   pasting in that platform's own registered OAuth app client id/secret.
   Drop the resulting auth config ids into `.env` as
   `COMPOSIO_<PLATFORM>_AUTH_CONFIG_ID`. This is the one thing that
   unblocks testing the actual connect flow end-to-end, and it's the
   biggest open question from this round — the real SDK signatures are
   verified, but a live connection through Composio's hosted authorize
   page to a real platform consent screen has not been seen firsthand.
2. **Once that's connected**: check whether Composio's
   `connected_accounts.retrieve()` response actually carries a usable
   display name/handle in its `data` field — resolves the
   "Connected-account display name" gap noted above.
3. **Confirm the "one recurring task" framing with the founder** —
   a prior round proceeded with "drafting weekly captions" as the
   recommended answer and built/reframed the product around it, but
   that's still his call to make, not something a build round settles
   on its own.
4. **Get a real `ANTHROPIC_API_KEY` in front of the Content Planner** —
   the biggest open question there is whether Claude's `draft_copy`
   output actually reads as publishable caption copy in practice, not
   just that the plumbing works.
5. **`priority_todolist.md`'s remaining stretch item**: a lightweight
   client switcher in the UI, once there's more than one client actually
   being worked day to day.
6. **Widen the multi-tenant trend-scoring fix** beyond the Content
   Planner (Strategy Consultant, Campaign Manager, Brand Collaboration,
   Trend Reports, `/trends` + `/recommended`) — worth doing once a
   second real client is onboarded and there's something to verify the
   ranking against, rather than guessing.
7. Once the above is settled: resume the phase-completeness track
   below. All non-credential-gated agent work identified so far is now
   built — Phase 2, Phase 3, Phase 4, and Phase 5 all fully closed out,
   and Phase 6's Platform Integration sub-agent as far as it can go
   without real credentials. Any further backend feature work is either
   credential-gated (Phase 6's Performance Tracking/Social
   Analytics/Channel Intelligence, Phase 5's remainder, Phase 3's
   competitor social/engagement tracking, Phase 4's Performance
   Discovery, Phase 2's social profile importer), ToS/legal-risk (Phase
   4's LinkedIn scraping), or needs a product/design decision first
   (graph UI, linking model, notification delivery channel — see the
   🟡 sections above).
8. When ready for the rest of credential-based testing: a real
   Postgres connection string for `alembic upgrade head` (15 migrations
   deep now — still only ever verified against SQLite via
   `Base.metadata.create_all()`, which bypasses Alembic entirely; note
   migration `0001` itself can't even compile against SQLite, so this
   has never been a close call).
9. Auth (Supabase Auth recommended) — worth moving up your own priority
   list given the "anyone can act on any company's connections" gap
   restated above, whenever you're ready to take it on. The
   `approved_by` free-text field from a prior round is a stopgap, not a
   substitute.
