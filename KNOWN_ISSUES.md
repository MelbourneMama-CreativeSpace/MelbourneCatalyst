# Known Issues & Incomplete States

## ✅ Resolved this round — per-company ownership, and the multi-tenant trend-scoring gap

Closes the longest-standing 🔴 item in this file and the 🟡 that was
explicitly waiting on it. These were the only two genuinely buildable
items left; everything else still open is blocked on a credential, a real
connected account, or a product decision (see the sections below, which
are unchanged).

### Per-company ownership — closes the 🔴 "any signed-in user can act on any company"

Since the Supabase Auth round, every route required a real session but
nothing tied a `Company` to the people allowed to touch it. Any signed-in
user could read, edit, publish, connect, or disconnect any company's data.

- **`company_members`** (migration `0027`) rather than a single
  `companies.owner_id`, because this app already assumes several people
  work one client — `approved_by`, `reviewer`, and the /approvals
  "Assign to me" toggle all predate this round. A single owner column
  would have needed replacing the first time a second person touched an
  account. `user_id` holds the Supabase `sub` as plain text, not a FK:
  `auth.users` lives in a schema this app has no business referencing,
  and which doesn't exist at all under SQLite in tests.
- **One chokepoint, not 159 sprinkled checks.**
  `app/security/ownership.py::ensure_company_access` is the only place
  that decides who may see what. It landed cheaply because this codebase
  already funnelled every company lookup through
  `_get_company_or_404` (5 duplicated copies) and
  `_get_ready_company_or_error` (3 more) — those were replaced by the
  shared helper rather than new call sites appearing everywhere.
- **404, never 403, for a company you're not a member of.** A 403 would
  confirm the id exists, turning an unguessable UUID into an oracle for
  enumerating other tenants. The response is byte-identical to a genuinely
  missing company. List endpoints and the dashboard's counts are filtered
  by the same predicate, so `total` can't leak how many other clients
  exist either.
- **Claim-on-first-access for companies that predate ownership.** They
  have no user to attribute them to, so there is nothing to backfill from
  — the first signed-in user to open one becomes its owner, and normal
  rules apply forever after. Documented as the one-time transition it is.
- **Invites without Supabase's Admin API.** `POST
  /companies/{id}/members` with an email stores an inert row; it binds to
  a real `user_id` the first time a token carrying that address reaches
  the company. This app never has to translate an email into a user id —
  it just waits for the person to arrive. No service-role key, and no
  unverifiable code path. It also sends no email, and the UI says so
  plainly rather than implying one went out.
- **Background jobs are deliberately left unguarded**, and the ownership
  module's docstring says so explicitly. The five scheduler jobs and
  `run_onboarding` legitimately sweep every company with no user at all;
  enforcement lives at the API layer for exactly that reason. A future
  round "tidying up" by pushing these checks down into the agent/graph
  modules would break every background job the moment it ran.

**Three holes that would have made the rest of it decorative**, each
found by walking the routes rather than by review:

1. `POST /companies` with an *existing* URL takes the re-onboard branch,
   which wipes that company's documents and restarts its onboarding —
   **no company id required, just the URL**. Without a check there, the
   whole feature could be walked around by anyone who could guess a
   client's website. Now 404s (not 403s) for a non-member, so it also
   can't be used to test whether a given URL is already onboarded.
2. **The chat agent was an unguarded side door.** Conversations had no
   owner at all (`ChatConversation` explicitly documented "No `user_id`"),
   and `/confirm-action` executed write tools against whatever id Claude
   had put in `tool_input` — an id ultimately derived from user-typed
   text, which is not evidence the caller may act on that row. Fixed at
   both ends: conversations now carry `user_id` (same migration) and are
   private to the person who had them, and every proposed action's target
   is re-resolved to a company and re-checked immediately before
   execution. A write tool addressing neither a company nor a content
   item is *refused* rather than run unchecked — the intended failure mode
   if someone adds a new write tool without extending that function.
3. **`GET /knowledge-base/search` takes an optional `company_id`**, so
   the unfiltered call ranked across every tenant's documents and returned
   their content verbatim — the worst single leak in the codebase. The
   membership predicate is now pushed into `similarity_search` itself, as
   a caller-supplied clause so that module (which background jobs also
   use) stays independent of the auth layer.

### Multi-tenant trend scoring — closes the 🟡, now that there's something to verify it against

`CompanyTrendRelevance` (migration `0014`) has scored every trend against
every company for several rounds, but only the Content Planner ever read
it. Strategy Consultant, Campaign Manager, Brand Collaboration, Trend
Reports, `/trends`'s `min_relevance` filter, and `/recommended` all still
read the legacy global `Trend.relevance_score` — a single number per
trend, scored against whichever company happened to be most recently
updated at collection time. Frequently the right score for the wrong
client.

The prior round declined to fix this in one pass, on the grounds that
doing it blind risked subtle ranking regressions across every generation
agent at once. That concern is addressed by structure rather than by
courage: the prefer-per-company-then-fall-back-to-global read that
already existed in `content_plan_graph.py` was extracted to
`app/agents/trend_analyzer/relevance.py`, and **all six remaining callers
plus the Content Planner itself now go through that one implementation**
— so there is no second copy that can drift, and the fallback is
preserved rather than dropped.

Two details worth knowing before touching it:

- **The legacy fallback is not vestigial.** A company onboarded since the
  last collection run has no `CompanyTrendRelevance` rows at all. Without
  the fallback those companies would silently get *no* trend context
  rather than imperfect trend context — a worse failure, and a much
  harder one to notice.
- **One caller opts out of it on purpose.** The Content Opportunity
  endpoint labels its prompt "this company's relevant trends", so
  `fallback_to_global=False` keeps its honest empty state ("no scored
  trends exist yet for this company") instead of passing off another
  company's scores as this one's. `fetch_scored_trends` also returns the
  score it actually ranked by, so no caller prints a global number next
  to a per-company ordering.

`recommendation.py` was deleted outright, superseded by `relevance.py`;
its three importers were updated. The chat agent's `list_trending_topics`
gained a `company_id` the dispatcher already knew how to inject, so a
company-scoped chat now ranks by that company's relevance too.

**Verified live, real and unmocked**: a consolidated script ran **32
checks against a real uvicorn process** over real HTTP, against a real
SQLite file DB, with **two genuinely different users** — real HS256 JWTs
going through `app/security/auth.py`'s actual decode path, not a
dependency override. User B was refused (404, never 403) on user A's
company, company list, dashboard counts, connections, drafts, approvals
queue, documents, and trend reports; the refused disconnect left the real
`PlatformConnection` row still `connected` with its Composio id intact,
the refused approval left the real `ContentItem` still `pending`, and the
refused URL re-onboard left A's real `Document` row in place.
Claim-on-first-access was confirmed by inspecting the `CompanyMember` row
the request actually wrote; an invite was confirmed to be inert until
binding, then to bind to a real user id in the database. And the
multi-tenant fix was proven end-to-end: the same two trends came back in
**opposite order** for a company-scoped versus an unscoped request, which
is exactly what a caller still reading the global score could not produce.
All 32 passed.

Backend suite: **539/539 passing** (up from 504 — 35 new tests, none
skipped or weakened; the 4 that broke were tests asserting old
cross-tenant behaviour or using placeholder ids, and were updated to
exercise the real path rather than relaxed). Frontend `npm run build`,
`npm run lint`, and `npx tsc --noEmit` all clean.

**Migration `0027` verified two ways**, since `alembic upgrade head`
still can't run end-to-end on SQLite (migration `0001`'s Postgres-only
`JSONB` blocks the chain, same standing caveat as every round since):
its `upgrade()` and `downgrade()` were run against a real SQLite
connection with a hand-built pre-0027 schema — confirming both unique
constraints are actually *enforced*, and that two pending invites with
`NULL user_id` still coexist (the thing that makes the invite design
work at all) — and the same migration was compiled through SQLAlchemy's
Postgres dialect so the DDL that would hit the real database is
generated, not assumed.

**Standing caveats, unchanged**: `ANTHROPIC_API_KEY` still has zero
credit. The real Supabase Postgres is still unreachable via DNS from this
dev environment, so `0027` has not been applied to it. And the live
verification above minted its own HS256 tokens against a local throwaway
secret — that exercises the real verification code path, but the real
project uses asymmetric JWKS signing, so a real signed-in browser session
end-to-end still depends on the sign-up step that's been yours to do
since the Auth round.

---

## ✅ Resolved previous round — the last three buildable items on the 21-item list

Closes out the "Suggested order for what's left" list from the previous
round's `FEATURE_STATUS.md`: #9 Content Repurposing Engine (was ⚪ not
built), #3 Content Opportunity Discovery (was 🟡 partial, waiting on #18's
real performance data — #18 shipped last round), and #11's reviewer
assignment refinement.

- **#9 Content Repurposing Engine** — one Claude call
  (`backend/app/agents/content_management/repurposing.py`) adapts an
  existing item's message for a different platform/format, creating a
  **new** `ContentItem` (not mutating the source) with a self-referential
  `repurposed_from_id` tracing it back — same shape as `source_trend_id`.
  Deliberately scoped narrower than the original suggestion (which
  imagined chunking a long transcript): every `ContentItem` in this app
  is already a short-form post, not a podcast/blog source, so honest
  "repurposing" here is cross-platform adaptation, not decomposition.
- **#3 Content Opportunity Discovery** — one Claude call
  (`backend/app/agents/trend_analyzer/opportunities.py`) over the
  company's own real data: its `CompanyTrendRelevance`-scored trends (the
  multi-tenant-correct table, reusing the exact join
  `content_plan_graph.py` already has), upcoming seasonal dates
  (`content_planner.py`'s `_seasonal_candidates` made public as
  `seasonal_candidates` for this reuse), and recent
  `PlatformMetricSnapshot` rows if any exist. Produces a structured,
  ranked list (title/reasoning/source/priority) — distinct from the
  existing weekly `TrendReport`'s free-text `content_opportunities`
  paragraph, which stays as-is.
- **#11 reviewer assignment** — a free-text `reviewer` column on both
  `ContentItem` and `Strategy` (same lightweight attribution pattern as
  `approved_by`), an All/Mine toggle and "Assign to me" button on
  `/approvals` reusing the existing `mmcs_approver_name` localStorage
  identity already used elsewhere for `approved_by` — no new identity
  system invented.

### A real bug caught mid-edit, not by review
Renaming `content_planner.py`'s `_seasonal_candidates` to the public
`seasonal_candidates` (for #3's reuse) via a blind find-and-replace also
renamed its call site's local variable assignment —
`seasonal_candidates = seasonal_candidates(today, days)` — which Python
treats as a local variable for the *entire* function body the moment
there's any assignment to that name, making the call on the right-hand
side reference the not-yet-assigned local instead of the module-level
function. This would have raised `UnboundLocalError` on every real content
plan generation. Caught immediately by re-running the affected test file
right after the rename (routine practice, not a special check) — fixed by
renaming the local variable to `seasonal_candidate_list` instead.

**Verified live, real and unmocked**: a consolidated script ran real,
unmocked checks against the local throwaway SQLite DB — a real repurpose
attempt (real Claude call, correctly 502'd on zero credit), a real
opportunities-generation attempt (real Claude call, correctly 502'd), and
a plain DB round-trip confirming `reviewer` persists on both `ContentItem`
and `Strategy`, appears correctly in the pending-approvals queue, and
that assigning one does **not** itself change `approval_status`. Backend
suite: **504/504 passing** (up from 483 last round). Frontend
`npm run build`/`npm run lint` both clean after every feature.

**Standing caveats, unchanged**: `ANTHROPIC_API_KEY` still has zero
credit. The real Supabase Postgres database is still unreachable via DNS
from this dev environment — two more migrations this round (`0025`
repurposed_from_id, `0026` reviewer) are written and fully tested against
a local throwaway SQLite copy, not yet applied to the real database.

**This closes out every genuinely buildable item on the original 21-item
list.** Only #17 Community Inbox remains, and only because it's
authentically blocked on a real connected account — see
`FEATURE_STATUS.md` for the full breakdown and what's needed to unblock
it and re-verify everything else against real external services.

---

## ✅ Resolved previous round — the credential-gated items weren't actually all blocked

You asked for the rest of the 21-item list: #18 Content Performance
Analytics, #16 Social Publishing Monitor, #19 Content Insights &
Recommendations, #14 Media & Asset Library (Supabase Storage), and
improvements to #6 AI Content Generation. Three of those four were
previously written off in `FEATURE_STATUS.md` as "genuinely blocked on
real credentials." Re-examining them for this round found that only one
piece is actually blocked — the rest were solvable with the same
discipline already used for #10's publishing:

- **#16 Social Publishing Monitor needed no new credentials at all.** It
  turns out "monitor what got published" doesn't need live platform
  data — it needs this app's own `PublishAttempt` log, which has existed
  since last round's publishing feature. `GET
  /social-media-analyzer/publish-attempts` (joined with content item +
  company, filterable) and a `/monitor` page with a retry button
  (`POST .../publish-attempts/{id}/retry`, logs a new attempt rather
  than mutating the old one). Fully real, fully tested, no "not
  configured" path needed anywhere in this one.
- **#18 Content Performance Analytics extends #10's exact pattern**:
  `COMPOSIO_<PLATFORM>_METRICS_TOOL_SLUG` settings (blank, same as the
  post tool slugs — you confirm the real slug once you have a Composio
  account and its catalog for that toolkit), `fetch_platform_metrics()`
  (`backend/app/agents/social_media_analyzer/metrics.py`) calling
  Composio's `tools.execute()`. The one thing kept deliberately honest:
  the full raw response is stored as-is in `PlatformMetricSnapshot
  .raw_metadata` — no code here guesses at a nested field-name schema
  for a platform response nobody in this project has ever seen.
  `follower_count`/`engagement_rate` are only opportunistically read
  from literal top-level keys, explicitly documented as best-effort. A
  new scheduler job (`run_scheduled_metrics_sync`, every 6 hours) and a
  manual sync endpoint both write into the schema that's existed empty
  since Platform Integration first shipped. A hand-built SVG sparkline
  (no new charting dependency — none existed in this app) renders real
  history on `/integrations/[companyId]` once any exists.
- **#19 Content Insights & Recommendations is one Claude call over real
  stored data** (`backend/app/agents/social_media_analyzer/insights.py`)
  — recent `PlatformMetricSnapshot` rows plus recently-published
  content, with the system prompt explicitly instructed to say plainly
  "not enough data yet" rather than invent a plausible-sounding insight
  when the input is thin. This is the one place this round where
  getting the "never fabricate" discipline right actually mattered more
  than the code itself.
- **#14 Media & Asset Library really was greenfield** — no file storage
  existed anywhere in this app. Used the official `supabase` Python SDK
  (chosen because you specifically said "use supabase storage"), but
  its real async API (`create_async_client`, `bucket.upload/remove
  /get_public_url` — and that `get_public_url` is itself a coroutine,
  which isn't obvious from the method name) was introspected against
  the actually-installed package before writing `storage.py`, same
  discipline as verifying `composio-client` two rounds ago. New
  `MediaAsset` table, upload/list/delete endpoints, a `/media
  /[companyId]` page. **A real, non-trivial side effect**: installing
  `supabase` bumped this project's pinned `pydantic` from `2.11.3` to
  `2.13.4` (a transitive dependency of the SDK) — the full backend test
  suite was re-run at the new version before accepting it, not assumed
  safe.
- **#6 AI Content Generation** gained the three missing formats
  (Threads as a platform; newsletter and podcast as content types) plus
  a structured `hashtags: list[str]` field on `ContentItem`, editable in
  the Draft Workspace — exactly the "how to build it" note already
  sitting in `FEATURE_STATUS.md` from the prior round.

**What's actually still blocked, for real**: #17 Community Inbox — needs
each platform's comments/DMs/mentions API, which is genuinely separate
integration work per platform and needs a real connected account to
verify response shapes against. That's the one item left in the
"genuinely blocked" category; everything else that used to be there is
now built.

**Verified live, real and unmocked, same discipline as every round**: a
single consolidated script ran five real, unmocked checks against the
local throwaway SQLite DB — content generation with the new Threads/
newsletter combination (real Claude call, correctly 502'd on zero
credit), a real publish-attempt retry (real Composio call, correctly
failed with "not configured" and logged a new attempt), a real media
upload attempt with no `SUPABASE_SERVICE_ROLE_KEY` set (correctly
409'd with the exact missing-config message), a real metrics sync
attempt with no tool slug set (correctly 409'd), and a real insights
generation call (correctly 502'd on zero credit). Backend suite:
**483/483 passing** (up from 448 before this round — new tests for
every feature, none skipped or weakened). Frontend `npm run build`/
`npm run lint` both clean after every feature, checked incrementally
not just at the end.

**Standing caveats, unchanged**: `ANTHROPIC_API_KEY` still has zero
credit. The real Supabase Postgres database is still unreachable via
DNS from this dev environment — three more migrations this round
(`0023` hashtags, `0024` media_assets) are written and fully tested
against a local throwaway SQLite copy, not yet applied to the real
database. New this round: `SUPABASE_SERVICE_ROLE_KEY` (Media Library)
and six `COMPOSIO_<PLATFORM>_METRICS_TOOL_SLUG` values (Performance
Analytics) join the standing list of "config slots deliberately left
blank until you can confirm the real value against a live account" —
see `.env.example` for all of them together.

---

## ✅ Resolved previous round — LoomVerse AI rebrand, dashboard/chat, and the 21-item feature list closed out

Since the last entry below, the app was rebranded (LoomVerse AI), got a
real dashboard + a tool-using chat assistant, and every "buildable now,
no new infrastructure" item from your 21-feature audit
(`FEATURE_STATUS.md`) was built across two build arcs. `FEATURE_STATUS.md`
is the detailed, per-feature living record — this entry is the summary.

**Arc 1 — your four stated priorities**: (1) AI content generation with a
humanized system prompt + KB-grounded style reference + manual single-topic
input; (2) a full content approval queue with a live sidebar badge; (3) a
Draft Workspace (`/drafts`) with editable drafts, revision history, and
comments; (4) Composio-backed publishing + APScheduler-driven scheduling
behind one shared `PublishPanel` component.

**Arc 2 — the rest of `FEATURE_STATUS.md`'s "buildable now" tier** (this
round, P1–P4):
1. **Content Knowledge Hub self-indexing** — approved `ContentItem`s and
   `Strategy`s now feed into the same `Document` table externally-scraped
   content already uses (`generated_content_indexing.py::index_on_approval`),
   so plain KB search and the chat agent's `search_knowledge_base` tool can
   finally find a company's own past approved content, not just scraped
   material.
2. **Content Quality Review + Brand Consistency Checker** — one Claude call
   (`content_management/quality_check.py`) reviews a draft's grammar/tone/
   formatting and brand-voice adherence together, persisted on the item and
   surfaced as a pass/fail banner in the Draft Workspace.
3. **Chat agent write tools, propose-then-confirm** — the chat assistant
   (previously read-only) can now approve/reject/regenerate a content item
   or create a new content plan, but never executes any of them itself:
   calling one ends the turn with a proposal (`ChatMessage.proposed_action`),
   rendered as a Confirm/Cancel card, only actually run via a dedicated
   `/confirm-action` endpoint. This was the one deliberately-deferred safety
   design decision from the read-only chat round, now built.
4. **Creative Brief Generator** — one Claude call produces a hook, shot
   list, visual references, editing notes, and (for video content) a
   thumbnail concept per content item, shown as a collapsible section
   alongside History/Comments in the Draft Workspace.

**Verified live, real and unmocked, same discipline as every round**: a
real approve-through-chat mutated a real `ContentItem` row *and* correctly
fed straight into the KB self-indexing hook (a genuine cross-feature
integration proof, not two isolated tests) — confirmed by inspecting the
resulting `Document` row directly; a double-confirm on the same proposal
correctly 409'd; a cancel correctly left the item untouched. The quality
check and creative brief endpoints were each called for real against the
real `ANTHROPIC_API_KEY` (still zero credit — see the standing 🔴 item
below) and correctly surfaced Anthropic's real "credit balance too low"
error as a clean 502, not a crash. Backend suite: **440/440 passing**.
Frontend `npm run build`/`npm run lint` both clean after every feature.

**Standing caveats, unchanged**: `ANTHROPIC_API_KEY` still has zero credit
— every Claude-dependent piece here is built, tested, and proven to fail
gracefully, but none has been seen producing real output yet (see the 🔴
item below). The real Supabase Postgres database is still unreachable via
DNS from this dev environment (`db.<project>.supabase.co`, IPv6-only AAAA
record) — all 7 new migrations across both arcs (`0016`–`0022`) are
written and fully tested against a local throwaway SQLite copy, but not
yet applied to the real database.

---

Audit compiled after eleven rounds. This round ran all 15 Alembic
migrations against a real Supabase Postgres database you provided a
connection string for — the first round in this project's history where
`DATABASE_URL` points at real, persistent storage instead of a
throwaway local SQLite file. Combined with the previous round's Supabase
Auth work, the app's storage and auth layers are both now real,
live-verified infrastructure, not just graceful-degradation paths. Real
usage against that real infrastructure the same day surfaced two more
findings: a genuine SSRF-guard bug that was blocking a real site from
onboarding (found and fixed — see below), and the actual current
blocker on content generation: `ANTHROPIC_API_KEY` is real and was
exercised against a live call for the first time, but the key has **zero
credit balance**, not a code problem. See `BUILD_STATUS.md` for the
founder-facing version of this finding. Everything in this file is
verified either by automated tests or by live requests against real
infrastructure: your real Supabase project (Auth + Postgres) and a
running frontend/backend. Current repo state: branch `business-analyzer`
(all eleven rounds' work, plus earlier rounds', not yet committed as of
writing this file).

**Backend tests: 346/346 passing (345 before this round's SSRF fix — 1
new regression test; was 331 before the Auth round, 338 before that, 320
before that, 315 before that, 305 before that, 296 before that, 258
before that, 241 before that, 209 before that, 178 before the OAuth
round). Frontend: lint/typecheck/build all clean.**

---

## ✅ Resolved this round — Real Supabase Postgres database, all 15 migrations run live

You provided a real Supabase DB connection string this round — the
first time in this project's history `alembic upgrade head` has run
against real Postgres instead of the SQLite `Base.metadata.create_all()`
workaround every prior round relied on. `backend/.env`'s `DATABASE_URL`
now points at your real project (direct connection, not the pooler —
correct for one-off migration runs).

- **All 15 migrations ran cleanly, 0001 through 0015**, confirming for
  the first time that migration `0001`'s Postgres-specific `JSONB`
  column (the exact thing that made SQLite untestable via Alembic every
  prior round) and every migration since — including the `pgvector`
  `embedding` column, all the FK/index definitions, and the Composio
  migration's column drops — are actually valid against real Postgres,
  not just plausible-looking.
- **A real, general Alembic bug found and fixed, not a one-off
  workaround.** `alembic/env.py` passed `DATABASE_URL` through
  `config.set_main_option()`, which routes through `configparser`'s
  interpolation — and `configparser` treats a bare `%` as the start of
  its own `%(name)s` syntax. Your password contains a URL-encoded `@`
  (`%40`), so migrations crashed immediately with `ValueError: invalid
  interpolation syntax`. This wasn't specific to your password — *any*
  DATABASE_URL with a percent-encoded character (which is normal for
  passwords containing `@`, `#`, `%`, spaces, etc.) would have hit this.
  Fixed by escaping `%` → `%%` before handing the URL to configparser,
  in `env.py` itself, so it's fixed for good, not just for this one
  connection string.
- `alembic current` confirms `0015 (head)`. All 15 tables plus
  `alembic_version` exist: `campaigns`, `collaboration_ideas`,
  `collaborations`, `companies`, `company_trend_relevance`,
  `competitors`, `content_items`, `content_plans`, `documents`,
  `knowledge_audit_reports`, `platform_connections`,
  `platform_metric_snapshots`, `strategies`, `trend_reports`, `trends`.

**Verified live**: backend restarted against the real `DATABASE_URL`,
`GET /health` 200, a direct query against the real `companies` table
returned `0` rows (correct — a fresh schema, not yet used), and the auth
gate still correctly 401s an unauthenticated request to
`/api/v1/companies/` — proving the DB switch didn't accidentally bypass
last round's auth work. Full backend suite re-ran and still passed
345/345 (the test suite uses its own isolated per-test DB via fixtures,
so it was never exercising the real connection either way — this is
what actually needed a real Postgres connection string to verify, and
now has been).

**A credential-hygiene note, not a blocker**: the DB password arrived in
plaintext in chat, same as the Supabase Auth keys two rounds ago. Worth
rotating via Supabase's dashboard (Project Settings → Database → Reset
database password) if you're ever unsure who's seen this conversation —
not urgent, just the same standing recommendation as before.

### A second real bug found the same day, by real usage — not a code review

You (or the founder, testing the running app) hit a real "Onboarding
failed: No pages could be scraped from the provided URL" error against a
real site, `melbournemamacreativespace.com`. Investigated live: the site
is genuinely reachable (confirmed `200 OK` via direct request), but
`app/security/__init__.py`'s SSRF guard was rejecting it. Root cause:
this environment's DNS resolver synthesizes a NAT64 IPv6 address
(`64:ff9b::/96`, RFC 6052) alongside the site's real IPv4 address for
IPv4-only hosts — a legitimate, globally-routable address, not an
internal one. The guard's `_is_public_ip` check used
`ipaddress.IPv6Address.is_reserved`, which is `True` for that prefix
(it's in IANA's special-purpose registry) even though it's publicly
reachable — so a real, safe site got wrongly blocked. **Fixed** by
switching to the stdlib's own `is_global` flag (the correct semantic:
"allocated for public networks") instead of a hand-rolled combination of
`is_private`/`is_loopback`/`is_link_local`/`is_reserved` — this also
closes a latent gap the old check had (CGN shared address space,
`100.64.0.0/10`, was previously being let through as "not private";
`is_global` correctly excludes it too). One new regression test added
(`test_allows_nat64_synthesized_address_alongside_real_ip`); full SSRF
suite and full backend suite both re-ran clean (346/346). Re-verified
live: re-scraping the same real site after the fix now returns 2 real
pages of content instead of 0.

### First real end-to-end test against a real site — and the one thing actually blocking a live demo

With a real database, real scraping, and a real `ANTHROPIC_API_KEY` all
in place for the first time simultaneously, ran the full onboarding
pipeline against `melbournemamacreativespace.com` for real (not
mocked). The scrape + persistence half worked completely — 4 real
document chunks stored against a real `Company` row in real Postgres.
The Claude-powered profile extraction half failed immediately with a
real, unambiguous error from Anthropic's API:
`"Your credit balance is too low to access the Anthropic API."` The
company row correctly landed in the existing `complete_no_profile`
status (a state this codebase already handles gracefully from an
earlier round) rather than crashing. **This is now the single concrete
blocker between "the content-drafting pipeline is built" and "here's a
real drafted caption"** — not a code gap, a billing one. See
`BUILD_STATUS.md` for the founder-facing writeup of this finding.

## ✅ Resolved previous round — Supabase Auth: login page + whole-app protection

You asked specifically for a login page "using supabase," then for the
broader scope: the whole app gated behind real sign-in, not just a
login form bolted on the side. This closes the **unauthenticated
access** half of the single longest-standing item in this file — every
round since Platform Integration first stored real OAuth tokens has
flagged "anyone who can reach the API can act on any company's data" as
deferred by your explicit choice. Every route now requires a real,
signed-in Supabase user. **What this round does not add**: per-company
ownership. `get_current_user` proves *who* is calling, but nothing yet
checks that the signed-in user is allowed to touch a given `company_id`
— any authenticated user can still act on any company's data, same as
before, just no longer *any anonymous request*. See the 🔴 item below for
what closing that fully would need.

- **Backend: every API route requires a valid Supabase session JWT.**
  New `app/security/auth.py` — a `get_current_user` FastAPI dependency
  reads `Authorization: Bearer <token>` (or an `access_token` query
  param, needed because the Composio OAuth `/authorize` link from last
  round is a plain `<a href>` browser navigation, not a fetch, so it
  can't carry a custom header). Applied at **two** levels deliberately:
  `main.py`'s `app.include_router(api_router, dependencies=[...])` for
  the real running app, *and* on each of the 6 endpoint files' own
  `router = APIRouter(dependencies=[...])` — the second was necessary,
  not redundant, because this codebase's test suite builds isolated
  `FastAPI()` apps directly around each endpoint module's router,
  bypassing `main.py` entirely. Discovered by watching all 331 existing
  tests keep passing unchanged after the first (main.py-only) attempt —
  the tell that the gate wasn't actually being exercised. `/` and
  `/health` stay public.
- **Handles both of Supabase's JWT signing modes, auto-detected.**
  Rather than assume your project's signing mode, `_decode()` inspects
  each token's own `alg` header: `HS256` verifies against a shared
  `SUPABASE_JWT_SECRET`; anything else (ES256/RS256, the newer default
  for new Supabase projects) verifies against your project's public
  JWKS endpoint via `PyJWKClient`, no secret needed. Your real project
  turned out to use the asymmetric-key mode — confirmed by decoding
  your pasted `anon` JWT locally (no network call) to derive the project
  URL, then live-`curl`ing the real JWKS endpoint and seeing a real
  ES256 key published there.
- **Frontend: `src/proxy.ts`** (Next.js 16 renamed `middleware.ts` →
  `proxy.ts` and `middleware()` → `proxy()` — confirmed via this
  project's own vendored docs, not assumed) refreshes the Supabase
  session on every request and redirects unauthenticated visitors of any
  page to `/login?redirectTo=<original path>`, and authenticated
  visitors away from `/login`. New `/login` page (sign in + sign up, via
  `@supabase/ssr`'s browser client). New `AuthHeader` component shows
  the signed-in user's email + sign-out, rendered from a server-fetched
  session in `layout.tsx`.
- **A real Turbopack build failure, and the actual fix, not a
  workaround.** The natural design — one `apiFetch` used by both Server
  and Client Components, branching on `typeof window` to pick a browser
  vs. server Supabase client via a dynamic `import()` — fails to build:
  Turbopack statically traces dynamic imports into the client bundle
  regardless of the runtime guard, and `next/headers` (which the server
  client needs) cannot ship to the browser. Fixed with genuine file-level
  separation instead of a trick: `lib/api.ts` stays client-bundle-safe
  (browser client only), and a new `lib/api-server.ts` (marked
  `import "server-only"`, a newly-added npm package that turns this into
  a build-time error instead of a runtime one if the split is ever
  violated) holds thin duplicate wrappers for the 12 GET calls actually
  made from Server Component pages. All 12 server `page.tsx` files
  updated to import from the new file.

**What's genuinely new this round versus every prior one**: this is the
first round tested against real, user-provided credentials rather than
graceful-degradation/failure paths only. The Supabase project is real
and was hit live — the login form's "Invalid login credentials" response
came from Supabase's actual auth API over the network, and the backend's
rejection of a forged token came from a real query against the actual
JWKS endpoint (confirmed via a deliberately-bogus `kid` producing "Unable
to find a signing key that matches" rather than any network error). I
did **not** create a real user account in your Supabase project even to
test the success path — account creation is something I don't do on your
behalf even in your own systems, so the first real sign-up is yours to
do through the running `/login` page. Everything short of that — the
redirect gate, the login form, real-network auth rejection, all 6
protected routers 401ing/503ing correctly — was verified live.

**Verified live**: backend started against your real `.env` (real
`SUPABASE_URL`, real `ANTHROPIC_API_KEY`, empty `SUPABASE_JWT_SECRET`
since your project uses JWKS mode) — `GET /health` and `GET /` 200 with
no token; `GET /api/v1/companies/` 401 with no token; a forged ES256
token with a bogus `kid` correctly 401'd after a real JWKS lookup; a
malformed token and a case-variant `bearer` header both handled
correctly. Frontend dev server started against your real
`.env.local` — visiting `/` unauthenticated redirected to
`/login?redirectTo=%2F`; submitting a wrong-password login attempt
returned Supabase's real `"Invalid login credentials"` message, proving
live connectivity end-to-end. `npm run build`, `npm run lint`, and
`npx tsc --noEmit` all clean; full backend suite 345/345 passing with
the real `.env` on disk (ruling out `pydantic-settings` picking up real
values in some unexpected way). 14 new tests in
`tests/security/test_auth.py` cover both signing modes, the
query-param fallback, and two end-to-end tests through a real mounted
FastAPI app.

**What's still unverified, and why**: the actual sign-up → session →
authenticated-request round trip through the real UI has not been seen
firsthand, since that first step is a real account creation I
deliberately left for you to do. Once you've signed up once through
`/login`, everything downstream (an authenticated page load, an
authenticated API call) is exercised by the exact same code path already
proven live above — there's no additional integration risk hiding behind
that one step, just an account I won't create for you.

## ✅ Resolved two rounds ago — Platform Integration migrated to Composio + dedicated integrations page

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

## ✅ Resolved three rounds ago — Content Studio: real drafts, one framing, honest numbers

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

## ✅ Resolved four rounds ago — Strategy approval workflow (Phase 5 / Phase 6 audit)

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

## ✅ Resolved five rounds ago — Phase 4 completion (Trend Matching + Trend Outputs)

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

## ✅ Resolved six rounds ago — Phase 3 completion (Business Analyst + Knowledge Manager)

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

## ✅ Resolved seven rounds ago — Phase 2 Knowledge Base completion

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

## ✅ Resolved eight rounds ago — Content Planner Agent completion (Phase 5)

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

## ✅ Resolved nine rounds ago — Trend Outputs + Knowledge Manager (Phase 4 / Phase 3)

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

## ✅ Resolved ten rounds ago — Platform Integration Agent (Phase 6)

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

### ~~No per-company ownership~~ — **closed this round**
Every route now requires a real Supabase session *and* verifies the
caller is a member of the company being acted on, via
`company_members` (migration `0027`) and the single
`app/security/ownership.py::ensure_company_access` chokepoint. See
"Resolved this round" at the top for the design, the three holes that
had to be closed alongside it, and the live two-user verification.

**What this round does not add**: roles that actually differ.
`CompanyMember.role` records `owner` vs `member`, but both have identical
access — the column exists so a future round can restrict destructive
actions (disconnecting a platform, deleting a company) without another
migration. If you want a teammate who can draft but not publish, that's
the next increment, and it's a small one now.

### `ANTHROPIC_API_KEY` has zero credit balance — this is the real blocker now
No longer "hasn't been tried" — it has, this round, for real, and failed
with an unambiguous answer: `"Your credit balance is too low to access
the Anthropic API."` The scrape/persistence half of onboarding a real
site worked completely; the Claude-powered profile extraction step is
where it failed. So this is not a code gap — the pipeline, the prompt,
and the `draft_copy`-must-be-publishable-copy requirement from three
rounds ago are all real and wired up — it's purely a billing/credits
problem on the key itself. Once real balance is added, the very next
step is re-running this same test and actually reading the generated
`draft_copy` output to judge whether it clears the "reads as publishable
copy" bar in practice. See `BUILD_STATUS.md` for the founder-facing
writeup.
Separately: no Composio account or registered platform OAuth app exists
in this environment, so no `PlatformConnection` has ever gone through a
real connect → platform consent → Composio callback cycle — only the
failure/graceful-degradation paths are live-verified (see above); a
successful connection is only verified via mocked tests.

---

## 🟡 Remaining: needs a product/design decision, not just a fix

- **~~Single-tenant assumption in Trend Matching~~ — reads are fixed this
  round; one write remains.** Every *reader* now goes through
  `app/agents/trend_analyzer/relevance.py`, so Strategy Consultant,
  Campaign Manager, Brand Collaboration, Trend Reports, `/trends`,
  `/recommended`, the Content Planner, and the chat agent all rank by the
  company's own `CompanyTrendRelevance` score (falling back to the legacy
  global one only when that company has none yet). See "Resolved this
  round" at the top.
  **Still true**: `score_relevance` in `trend_analyzer/graph.py` also
  writes a single global `Trend.relevance_score` against "the most
  recently updated `complete` Company." Nothing reads it any more except
  as the documented fallback, so it's no longer a correctness problem —
  but it is now dead weight computed on every collection run, and worth
  deleting once you're confident the fallback is never the path that
  matters (i.e. once every onboarded company has been through at least
  one collection run).
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
priority has been `priority_todolist.md` and, the last three rounds,
Platform Integration's Composio migration, Supabase Auth, and this
round's real Postgres migration run, all by your explicit request rather
than the next phase in sequence. In order:

1. **Sign up for real through the running `/login` page** — the one
   step the Auth round deliberately left for you (see "Resolved previous
   round" above). Everything downstream of a real session is already
   live-verified against real Postgres now too; this just confirms the
   first hop. **More consequential than it was**: the first person to
   sign in and open each existing company now becomes its owner
   (claim-on-first-access), so it should be you or the founder, not a
   test account you throw away.
2. ~~**Per-company ownership**~~ — done this round. The follow-up, if you
   want it, is making `CompanyMember.role` actually mean something (an
   owner who can disconnect platforms vs. a member who can only draft);
   the column is already there.
3. **Set up Composio for real**: create a `COMPOSIO_API_KEY`, then in
   Composio's dashboard create one `use_custom_auth` config per platform
   you want live (Instagram, Facebook, X, LinkedIn, TikTok, YouTube),
   pasting in that platform's own registered OAuth app client id/secret.
   Drop the resulting auth config ids into `.env` as
   `COMPOSIO_<PLATFORM>_AUTH_CONFIG_ID`. This is the one thing that
   unblocks testing the actual connect flow end-to-end — the real SDK
   signatures are verified, but a live connection through Composio's
   hosted authorize page to a real platform consent screen has not been
   seen firsthand.
4. **Once that's connected**: check whether Composio's
   `connected_accounts.retrieve()` response actually carries a usable
   display name/handle in its `data` field — resolves the
   "Connected-account display name" gap noted above.
5. **Confirm the "one recurring task" framing with the founder** —
   a prior round proceeded with "drafting weekly captions" as the
   recommended answer and built/reframed the product around it, but
   that's still his call to make, not something a build round settles
   on its own.
6. **Top up the `ANTHROPIC_API_KEY`'s credit balance** — this is now the
   single concrete blocker on the whole Content Studio value
   proposition (see the 🔴 item above). Everything downstream is ready
   to test the moment there's balance: re-run onboarding against a real
   site, generate a strategy, generate a week of content, and actually
   read the `draft_copy` output to judge whether it clears the "reads as
   publishable copy" bar in practice.
7. **`priority_todolist.md`'s remaining stretch item**: a lightweight
   client switcher in the UI, once there's more than one client actually
   being worked day to day.
8. ~~**Widen the multi-tenant trend-scoring fix**~~ — done this round,
   bundled with #2 as suggested. The remaining scrap is deleting
   `score_relevance`'s now-unread global write (see the 🟡 section
   above), which is safe to do once every onboarded company has been
   through at least one collection run.
9. Once the above is settled: resume the phase-completeness track
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
