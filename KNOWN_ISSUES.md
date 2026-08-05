# Known Issues — LoomVerse AI

A defect register, not a build log. Every entry below was found by a
dedicated debugging pass: driving the real endpoint functions against a
real database as a user would, probing adversarially for cross-tenant
leakage / malformed input / concurrency, and reading the hot paths.

Each item says **how it was found** and **how to fix it**. Items marked
**Verified** were reproduced live in this pass, with the reproducing
behaviour described. Items marked **By inspection** are code-path
analysis where the trigger needs a deployment shape this environment
can't produce (e.g. multiple workers).

Build history lives in git; per-feature status lives in
`FEATURE_STATUS.md`. This file is only about what's wrong.

**Test-suite health:** 504 backend tests pass, frontend `build`/`lint`
clean. **Every defect below survived that suite** — see "Why the tests
didn't catch these" at the bottom, which is arguably the most important
item in this document.

---

## 🔴 Critical — data integrity / tenant isolation

### C1. One client's content can be published to another client's social account
**Verified.** `publish_now` (`backend/app/api/v1/endpoints/social_media_analyzer.py`)
validates that `item.platform == connection.platform`, and nothing else.
It never checks that the content item and the platform connection belong
to the **same company**. Reproduced: created Client A's item and Client
B's connected Instagram account, then called
`publish_now(client_B_connection, client_A_item)` — accepted, no error,
went straight to the Composio call.

Right now the only thing stopping a real mis-post is that no Composio
key is configured, so the call fails anyway. **The moment a real key is
added, this is a live cross-client data leak** — Client A's unpublished
copy posted to Client B's public feed.

`retry_publish_attempt` inherits the same gap (it trusts the stored
`platform_connection_id`), and the frontend doesn't protect you either —
it just happens to pass a matching connection today.

**Fix:** in `publish_now` and `retry_publish_attempt`, load the item's
`ContentPlan` and assert `content_plan.company_id == connection.company_id`,
409 otherwise. Add a regression test that asserts the mismatch is
rejected — there is currently no test anywhere that mixes two companies.

### C2. Any signed-in user can read and modify every client's data
**Verified** (by inspection of the whole app — grep confirms no
ownership column or check exists anywhere).

Supabase Auth proves *who* is calling. Nothing checks *what they're
allowed to touch*. There is no `owner_id` on `Company`, no membership
table, and no endpoint anywhere filters by the calling user. Any
authenticated account can list every company, read every draft, approve
anything, connect/disconnect any social account, and publish on anyone's
behalf.

This is the longest-standing hole in the app and was previously logged as
a deliberate deferral. It should stop being deferred: the app now stores
real client content and brokers real social-account access, so the blast
radius is materially larger than when the decision was made.

**Fix:** add `companies.owner_id` (or a `company_members` join table if a
client is worked by a team), then a shared dependency that resolves
`company_id` → authorized-or-403 and is applied to every company-scoped
route. Roughly a day's work; it touches every endpoint file but the
change is mechanical and testable.

---

## 🟠 High — real user-facing breakage

### H1. Two concurrent "add a draft" clicks permanently break manual-add and repurpose for that client
**Verified.** `_get_or_create_manual_plan`
(`backend/app/api/v1/endpoints/content_management.py`) does a
`SELECT ... WHERE company_id = ? AND is_manual IS TRUE` followed by
`scalar_one_or_none()`, then inserts if missing. There's no unique
constraint on `(company_id, is_manual)` in the schema, so two
simultaneous requests both see "none" and both insert.

From that point on, `scalar_one_or_none()` raises
`MultipleResultsFound` on **every** subsequent call — meaning manual
draft creation *and* the Repurpose feature return HTTP 500 for that
client forever, until someone manually deletes a row from the database.
Reproduced by seeding the post-race state and calling the helper.

**Fix:** add a partial unique index on `(company_id)` where
`is_manual IS TRUE` (migration), and catch `IntegrityError` on insert to
re-select — the standard get-or-create pattern. Until the migration
lands, `.limit(1)` + `scalar_one_or_none()` at least stops the permanent
500.

### H2. A malformed tool call from Claude 500s the chat confirm endpoint and jams the proposal forever
**Verified.** `confirm_action` (`backend/app/api/v1/endpoints/chat.py`)
executes `await impl(session, **action["tool_input"])` with **no
validation** of `tool_input` — which is raw model output that was stored
without ever being checked against the tool's signature.

Reproduced with a plausible model slip (`item_id` instead of
`content_item_id`, plus an extra `reason` key):
`TypeError: approve_content_item() got an unexpected keyword argument 'item_id'`
→ HTTP 500.

Worse, it's **unrecoverable through the UI**: `action_status` is only set
to `"confirmed"` *after* `impl()` returns, so a raising tool leaves the
row `"pending"` forever. Confirmed the message was still `pending` after
the 500. Every Confirm retry 500s again and the card never leaves the
screen. (Cancel does still work as an escape hatch, but nothing in the UI
tells the user that.)

**Fix:** validate `tool_input` against the tool's declared schema before
storing the proposal *and* again before executing it; wrap the call so
any failure marks the proposal `"failed"` and returns a clean 502 with
the real reason.

### H3. Approving from the Approvals queue silently erases who approved it
**Verified.** `update_content_item` runs
`item.approved_by = payload.approved_by` unconditionally whenever
`approval_status` is present. The `/approvals` page never sends
`approved_by` — only the calendar and strategy pages do.

So: approve an item on the calendar as "Priya" (recorded correctly), then
touch it from the Approvals queue → `approved_by` is nulled. Reproduced
directly. `update_strategy_approval` has the identical bug.

The whole point of `approved_by` is an audit trail for a small team, and
the app's own primary approval surface is what destroys it.

**Fix:** only assign when the field is actually provided
(`if payload.approved_by is not None:`), and have the Approvals page send
the stored reviewer name it already has in `localStorage`.

### H4. Threads drafts can be created but never opened
**Verified.** `threads` is a valid `Platform` in `api.ts`, is offered in
the manual-draft form, and is a legal target for content generation and
repurposing. But `frontend/src/app/(dashboard)/drafts/page.tsx` has a
hardcoded `PLATFORMS` tab list that omits it (instagram, linkedin,
twitter, tiktok, youtube, facebook, blog).

The Draft Workspace filters strictly by `item.platform === activePlatform`,
so a Threads draft is invisible: no tab renders it, and there is no
"other" bucket. It's created, stored, billed for, and unreachable.

**Fix:** derive the tab list from the `Platform` union instead of
duplicating it, or at minimum add `threads`. The duplication is the real
defect — the same drift will recur on the next platform added.

### H5. Failed generations sit in the approvals queue asking to be approved
**Verified.** When Claude generation fails, a `Strategy` row persists
with `status="failed"` and every content field `NULL` — but
`approval_status` stays `"pending"`. `list_pending_approvals` filters
only on `approval_status` and never checks `status == "complete"`.

Result: the queue shows a row titled "Strategy pending review" (the
placeholder used when `summary` is null), asking a human to approve or
reject an empty failed generation. Every failed attempt permanently
inflates the sidebar badge count. Reproduced — after one failed strategy
generation the badge showed 1 pending item that is pure noise.

**Fix:** add `Strategy.status == "complete"` to the queue query (and the
equivalent for content items), and have failed generations skip the
approval lifecycle entirely.

### H6. Running more than one web worker will double-post to social media
**By inspection** — needs a multi-worker deployment this environment
can't produce, but the code path is unambiguous.

`main.py`'s `lifespan` starts an `AsyncIOScheduler` unconditionally, so
**every** uvicorn worker / container replica runs its own copy of
`run_scheduled_publishing` and `run_scheduled_metrics_sync`.
`max_instances=1` only prevents overlap *within one process*.

`run_scheduled_publishing` selects due item IDs, then `_attempt_publish`
re-reads each and checks `published_at is not None`. That check is a
plain read with **no row lock, no claim, no unique guard** (grep confirms
zero `with_for_update` / advisory locks anywhere). Two workers can both
pass it and both publish the same item.

The app has only ever been run single-process, so this hasn't bitten —
but `uvicorn --workers 4` or a 2-replica deploy turns it into duplicate
public posts, which is a hard-to-undo, client-visible failure.

**Fix:** either claim rows atomically
(`UPDATE ... SET published_at=now() WHERE id=? AND published_at IS NULL`
and only publish if rowcount is 1), or move the scheduler out of the web
process entirely into a dedicated single-instance worker. The second is
the more durable answer.

---

## 🟡 Medium — degradation, scale, and honesty gaps

### M1. Chat replays unbounded history — conversations eventually break and cost grows quadratically
**Verified.** `send_message` rebuilds the Claude payload from **every**
prior message in the conversation, with no windowing, truncation, or
summarisation. Measured a 60-message conversation at ~30,400 characters
of replayed context; nothing caps it.

A long-running chat will eventually exceed the model's context window,
at which point *every* further turn fails permanently. Before that, token
cost per turn grows linearly with length — so total cost of a
conversation grows quadratically.

**Fix:** cap replayed history (last N messages, or a token budget), and
optionally roll older turns into a running summary.

### M2. Conversation list doesn't sort by recent activity
**Verified.** `listConversations` orders by `updated_at DESC`, but
sending a message only inserts a `ChatMessage` — the parent
`ChatConversation` row is never touched, so `updated_at` keeps its
creation timestamp. Confirmed `created_at == updated_at` on a
conversation with 60 messages.

The sidebar list is therefore ordered by creation, not activity: an old
conversation you're actively using stays buried.

**Fix:** touch the conversation (bump `updated_at`) when appending a
message.

### M3. No pagination anywhere on the cross-company lists — on the hottest path
**Verified.** `list_pending_approvals` and `list_content_items` both
return every matching row across every company with no `LIMIT`.

The Draft Workspace then pulls *all* drafts into the browser and filters
by platform in JavaScript. And the sidebar badge calls
`listPendingApprovals()` in a `useEffect` keyed on `pathname` — so a
growing, unbounded, multi-table join re-runs on **every single route
change**.

Fine at today's data volume; it degrades continuously and the first
symptom will be a sluggish sidebar, which is a confusing thing to debug.

**Fix:** add `limit`/`offset` to both endpoints, return a `total`, and
give the badge a cheap dedicated count endpoint (`SELECT COUNT(*)`)
rather than fetching full rows.

### M4. The frontend swallows errors — several failures show the user nothing
**By inspection**, consistent across components:

- `draft-card.tsx` — `handleSave` and `handlePostComment` use
  `try/finally` with **no `catch`**. A failed save just stops the
  spinner; the button returns to "Save" with no error, so the user
  reasonably believes the edit was stored when it wasn't.
- `draft-card.tsx` — `toggleHistory` and `toggleComments` have **no
  error handling at all**. A failed fetch leaves state `null`, so the
  panel shows "Loading…" forever.
- `publish-panel.tsx` — `handlePublishNow`, `handleSchedule` and
  `handleClearSchedule` all `try/finally` with no `catch`. Publish
  failures that come back as HTTP errors (404/409, as opposed to the
  200-with-`status:"failed"` shape) vanish silently.

Note this is *inconsistent* with the rest of the app — the quality
check, creative brief, repurpose, media, and insights handlers all do
have proper `catch` + error state. These are the stragglers.

**Fix:** add `catch` + an error message to each, matching the pattern
already used by the newer handlers in the same files.

### M5. Knowledge-Base self-indexing writes permanently unsearchable rows without a Voyage key
**Verified** as a chain, live: approving a content item logged
`VOYAGE_API_KEY not configured; skipping embedding` and still created the
`Document` row.

`similarity_search` filters `WHERE Document.embedding IS NOT NULL`. So
without `VOYAGE_API_KEY`, every approval silently writes a row that can
**never** be returned by search — the feature reports success and
produces nothing usable. Nothing warns anyone; the row just sits there.

**Fix:** surface the degraded state (a flag on the response, or a health
indicator on the KB dashboard), and add a backfill path to embed rows
that were stored without one once a key exists.

### M6. Chat failure messages look like real answers after a page refresh
**Verified.** `ChatMessageOut.ok` is deliberately not a DB column — it's
attached at send time. The UI uses it to render graceful-degradation
replies in a visibly distinct "Not available" style.

But on reload, `get_conversation` returns `ok=None` for every stored
message, so *"Something went wrong answering that — try again."* renders
as a normal assistant bubble. The honest-UI signalling only survives
until the page refreshes.

**Fix:** persist the flag (a nullable `ok` / `degraded` column on
`ChatMessage`) so the distinction survives a reload.

### M7. The public landing page misdescribes the product
**Verified in a browser** at `/` (which is correctly public and renders
without auth).

The copy is stale relative to what now exists: it presents the app as
"Content Studio's five agents", states **"Analytics — Not built yet"**
(Content Performance Analytics and Insights both ship now), and files
Trend Analyzer and the knowledge base under *"still in development,
reachable directly but not the focus yet"* — both are built. It never
mentions the dashboard, chat assistant, Draft Workspace, approvals,
publishing, publish monitor, or media library.

It's also the only unauthenticated page, so it's the first thing a real
prospect sees, and there's no visible sign-in/sign-up affordance — every
CTA points at a gated route and bounces you to `/login`.

**Fix:** rewrite `frontend/src/app/page.tsx` against current
`FEATURE_STATUS.md`, and add an explicit "Sign in" link to the nav.

---

## ⚪ Environmental blockers — not code defects

These are unchanged and outside the codebase's control. They are the
reason several features are built-and-tested but not *proven* against
real external data.

| Blocker | Effect |
|---|---|
| `ANTHROPIC_API_KEY` has **zero credit balance** | Every Claude feature returns a correct 502/degraded response instead of real output. Confirmed live again in this pass across all 9 generation endpoints. No Claude-generated content has ever been seen. |
| Real Supabase Postgres **unreachable via DNS** from this environment | Migrations `0016`–`0026` are written and tested against local SQLite only — **not applied to the real database**. This is the single highest-priority operational task. |
| No Composio account / connected social account | Publishing and metrics fail at the "not configured" gate. The per-platform tool slugs (`COMPOSIO_*_POST_TOOL_SLUG`, `COMPOSIO_*_METRICS_TOOL_SLUG`) are deliberately blank — never guessed. |
| No `SUPABASE_SERVICE_ROLE_KEY` / storage bucket | Media Library uploads correctly 409 with setup instructions. |

### Dev-vs-production divergences these create
Worth knowing because they make local testing quietly weaker than it looks:

- **FK cascades don't fire on SQLite.** Verified: deleting a company left
  its content items orphaned. SQLite ignores `ondelete="CASCADE"` unless
  `PRAGMA foreign_keys=ON` is set per connection, which this app never
  does. Postgres will cascade correctly — so local testing cannot
  validate any delete behaviour.
- **Semantic search always returns `[]` on SQLite.** So every locally-run
  KB-grounded feature is silently running without its grounding context.

---

## Why the tests didn't catch any of this

504 tests pass. All 15 defects above survived them. That's a coverage
*shape* problem, not a coverage *volume* problem, and it's worth fixing
before adding more tests:

1. **Every test is single-tenant.** No test anywhere creates two
   companies and tries to cross the boundary. C1 and C2 are invisible to
   a suite built this way.
2. **External output is always well-formed.** Claude and Composio are
   mocked with valid, complete responses. H2 (malformed `tool_input`)
   cannot occur in a suite that never emits a malformed tool call.
3. **Nothing tests concurrency or repeated state.** H1 needs two racing
   requests; H6 needs two workers. Both are shaped as "run once, assert".
4. **Field-clobbering isn't asserted.** Tests check that a PATCH sets
   what it sends; none assert that it *preserves* what it didn't send.
   That's exactly H3.
5. **Frontend has no tests at all.** `build` and `lint` pass — neither
   can see H4 (a missing tab) or M4 (a missing `catch`).

**Suggested additions, in value order:** a two-company cross-tenant test
helper used across every company-scoped endpoint; malformed/hostile
model-output fixtures for the chat write-tool path; "PATCH preserves
unsent fields" assertions on both update endpoints; and a smoke test that
every value in the `Platform` union is reachable in the Draft Workspace.

---

## Suggested fix order

1. **C1** — cross-tenant publish. Small, contained fix; it's the one
   defect that becomes an irreversible client-visible incident the day a
   Composio key is added.
2. **Apply migrations `0016`–`0026` to the real database.** Nothing else
   ships until this happens.
3. **H1, H2, H3, H5** — each is small and each currently corrupts state
   or hard-breaks a workflow.
4. **H6** — before any multi-worker or multi-replica deploy. Cheap now,
   very expensive to discover in production.
5. **C2** — per-company ownership. Larger and mechanical; schedule it
   deliberately rather than squeezing it in.
6. **H4, M1–M7** — real but non-destructive; order by what your team
   trips over first.
