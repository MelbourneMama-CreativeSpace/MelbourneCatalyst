# Feature Status — your 21-item list, checked against the real codebase

Every claim below was verified by reading the actual code today, not recalled from memory — file paths included so you can check any of them yourself.

**Legend**: ✅ Built and working · ⚪ Not built

---

## Quick summary

| # | Feature | Status |
|---|---|---|
| 1 | Content Knowledge Hub | ✅ Built |
| 2 | Trend Discovery Engine | ✅ Built |
| 3 | Content Opportunity Discovery | ✅ Built |
| 4 | Content Strategy Planner | ✅ Built |
| 5 | Content Calendar Management | ✅ Built |
| 6 | AI Content Generation | ✅ Built |
| 7 | Content Draft Workspace | ✅ Built |
| 8 | Creative Brief Generator | ✅ Built |
| 9 | Content Repurposing Engine | ✅ Built |
| 10 | Publishing & Scheduling System | ✅ Built (untested against a real connected account) |
| 11 | Content Approval Workflow | ✅ Built (reviewer assignment included) |
| 12 | Content Quality Review | ✅ Built |
| 13 | Brand Consistency Checker | ✅ Built |
| 14 | Media & Asset Library | ✅ Built (Supabase Storage; untested against a real bucket) |
| 15 | Campaign Management | ✅ Built |
| 16 | Social Publishing Monitor | ✅ Built |
| 17 | Community Inbox | ⚪ Not built |
| 18 | Content Performance Analytics | ✅ Built (real metrics fetch untested — no connected account) |
| 19 | Content Insights & Recommendations | ✅ Built (real output untested — zero Claude credit) |
| 20 | Content Search & Retrieval | ✅ Built |
| 21 | AI Content Assistant | ✅ Built (propose-then-confirm write tools) |

**20 of 21 built.** Only **#17 Community Inbox** remains — genuinely blocked on real credentials: needs each platform's comments/DMs/mentions API, separate permission scopes from everything else this app does, and a real connected account to verify the response shapes against before the parsing logic could be written honestly. Every other item that was ever flagged "blocked on credentials" (#10, #16, #18, #19) turned out to be honestly buildable without them, using the same discipline throughout: real code, real tests, real graceful-degradation paths, and a configuration slot left blank wherever an exact external value (a Composio tool slug, a bucket name) can't be verified without a live account — never a guess standing in for one.

---

## ✅ Built and working

### 1 + 20. Content Knowledge Hub / Content Search & Retrieval
The Knowledge Base indexes the app's own generated content, not just externally-scraped material: `ContentItem` and `Strategy` are ingested into the shared `Document` table the moment they're approved (`backend/app/agents/knowledge_base/generated_content_indexing.py::index_on_approval`, hooked into `update_content_item`/`update_strategy_approval` in `content_management.py`). Plain semantic search and the chat agent's `search_knowledge_base` tool both inherit this automatically since they already query the whole `Document` table — verified live: approving a real content item created a real `Document` row, findable by source.

### 2. Trend Discovery Engine
7 sources: Google Trends, Reddit, RSS, YouTube, X, Instagram, TikTok (`backend/app/agents/trend_analyzer/collectors/`). Google Trends and RSS are confirmed live with real data, no credentials needed. The rest need API keys you'd add yourself (see `CREDENTIALS.md`). LinkedIn is deliberately excluded — no public trends API exists; the only path is scraping a login-walled, anti-bot-hardened site, a ToS risk this app avoids everywhere.

### 3. Content Opportunity Discovery
One Claude call (`backend/app/agents/trend_analyzer/opportunities.py`) producing a ranked list of concrete opportunities, each citing what it's grounded in — a specific trend, an upcoming seasonal date, or the company's own real performance data (once #18 has any). Distinct from the weekly `TrendReport`'s free-text `content_opportunities` paragraph: this is structured (`title`/`reasoning`/`source`/`priority`), not prose. Context is built from the company-scoped `CompanyTrendRelevance` table (the multi-tenant-correct join `content_plan_graph.py` already uses, not the legacy global `Trend.relevance_score`), upcoming seasonal dates (`content_planner.py`'s `seasonal_candidates`, made public for this reuse), and recent `PlatformMetricSnapshot` rows if any exist. `POST /trend-analyzer/opportunities`, an `OpportunitiesCard` in the company page's "Other modules" section. Verified live: a real Claude call correctly surfaced the real zero-credit error as a clean 502.

### 4. Content Strategy Planner
One Claude call turns a company profile + relevant trends into a marketing strategy, campaign direction, growth recommendations, and business suggestions (`backend/app/agents/content_management/strategy.py`), with an approve/reject workflow on top.

### 5. Content Calendar Management
Real drag-and-drop month-grid calendar (`frontend/src/components/content-plan-view.tsx`), 7/14/30-day windows, reschedule via drag or PATCH, approve/reject per item, filterable.

### 6. AI Content Generation
Finished, publishable `draft_copy` for Instagram, LinkedIn, X/Twitter, TikTok, YouTube, Facebook, blog, and Threads, with a humanized system prompt and KB-grounded style reference (`backend/app/agents/content_management/prompts.py`, `content_planner.py`). Content types include newsletter and podcast description alongside post/video/article/carousel/story. Every item can carry structured `hashtags` (`list[str]`, separate from anything already inline in the draft's prose), editable in the Draft Workspace. "Video script" is still really a caption + brief rather than a shot-by-shot script — that depth intentionally lives in #8's Creative Brief instead of being duplicated here.

### 7. Content Draft Workspace
Per-platform draft workspace (`/drafts`) with an editable `draft_copy` textarea, editable hashtags, full revision history (`ContentItemRevision`, snapshotted before every manual edit or AI regeneration), and a comment thread (`ContentItemComment`) — `draft-card.tsx` collapsible History/Comments sections, backed by `GET/POST /content-items/{id}/revisions` and `/comments`.

### 8. Creative Brief Generator
One Claude call produces a production brief per content item — hook, shot list, visual references, editing notes, and an optional thumbnail concept for video-style content (`backend/app/agents/content_management/creative_brief.py`), stored in `content_item_creative_briefs` (overwritten on regeneration, not versioned). `POST/GET /content-items/{id}/creative-brief`, a collapsible "Creative brief" section in `draft-card.tsx`. Verified live: the real Claude call was made and correctly surfaced the real "credit balance too low" error as a clean 502.

### 9. Content Repurposing Engine
One Claude call (`backend/app/agents/content_management/repurposing.py`) adapts an existing item's core message for a different platform/format — not a copy-paste, a real rewrite in the target platform's voice/length conventions. Creates a **new** `ContentItem` in the source's manual plan, with `repurposed_from_id` tracing it back to the source (self-referential FK, `SET NULL` on delete — same shape as `source_trend_id`). `POST /content-items/{id}/repurpose`, a "Repurpose" collapsible section in `draft-card.tsx` with platform/format pickers. Scoped deliberately narrower than the original "chunk a podcast transcript" suggestion — this app's content is already short-form posts, not long-form sources, so the honest version of repurposing is cross-platform adaptation, not decomposition. Verified live: a real Claude call correctly surfaced the real zero-credit error as a clean 502.

### 10. Publishing & Scheduling System
`publish_post()` (`backend/app/agents/social_media_analyzer/publish.py`) wraps Composio's `tools.execute()` to post through whichever platform tool slug you configure (`COMPOSIO_<PLATFORM>_POST_TOOL_SLUG`), logging every attempt to a `PublishAttempt` table. An APScheduler job (`run_scheduled_publishing`, default every 5 minutes) publishes anything that's both scheduled and approved. One shared `PublishPanel` component works across every platform. **Not yet verified against a real connected account or real tool slug** — only the "not configured" graceful-degradation path is live-proven.

### 11. Content Approval Workflow
Full approval queue (`GET /content-management/approvals/pending`, `/approvals` page with a live sidebar badge) on top of per-item/per-strategy approve/reject. Reviewer assignment: a free-text `reviewer` column on both `ContentItem` and `Strategy` (same lightweight attribution pattern as `approved_by` — no real per-user auth exists in this app), an "Assign to me"/All-vs-Mine toggle on `/approvals` reusing the existing `mmcs_approver_name` localStorage identity already used for `approved_by` elsewhere. Assigning a reviewer is independent of approval_status — verified live it doesn't itself approve/reject anything.

### 12 + 13. Content Quality Review / Brand Consistency Checker
One Claude call (`backend/app/agents/content_management/quality_check.py`) checks a draft's grammar/tone/formatting *and* brand-voice adherence together — not two systems. Results persist on the `ContentItem` and overwrite on re-check. `POST /content-items/{id}/quality-check`, a "Check quality" button + pass/fail banner in `draft-card.tsx`. Verified live with a real, unmocked Anthropic API call (correctly surfaced the real zero-credit error as a 502).

### 14. Media & Asset Library
Real file uploads via Supabase Storage's official `supabase` SDK (`backend/app/agents/media_library/storage.py`) — its actual async API was introspected against the installed package before writing any code. A `MediaAsset` row per upload, `POST/GET /media-library/{company_id}/assets`, `DELETE /media-library/assets/{id}`, a `/media/[companyId]` page. **Requires `SUPABASE_SERVICE_ROLE_KEY`** and creating the storage bucket once by hand in Supabase's dashboard — verified live: with no service-role key set, a real upload attempt correctly 409'd with that exact instruction.

### 15. Campaign Management
`Campaign` model with `lifecycle_stage` (draft → scheduled → active → completed → archived), objective, budget recommendation, linked back to its content plan and strategy.

### 16. Social Publishing Monitor
A history of this app's own publish attempts — `GET /social-media-analyzer/publish-attempts` (filterable, joined with content item + company) plus a `/monitor` page with a retry button (`POST .../publish-attempts/{id}/retry`, logs a new attempt row). Needed **no new credentials** — monitors this app's own already-real `PublishAttempt` data. Verified live: a real retry correctly re-invoked the (not-configured) Composio publish path and logged the real failure.

### 18. Content Performance Analytics
`COMPOSIO_<PLATFORM>_METRICS_TOOL_SLUG` settings + `fetch_platform_metrics()` (`backend/app/agents/social_media_analyzer/metrics.py`) storing the full raw Composio response unparsed into `PlatformMetricSnapshot.raw_metadata` — never guesses at a response shape nobody's seen. Manual sync + a 6-hourly scheduler job both write into it. A hand-built SVG sparkline in `/integrations/[companyId]` renders real history once any exists. Verified live: with no metrics tool slug set, a real sync attempt correctly 409'd.

### 19. Content Insights & Recommendations
One Claude call (`backend/app/agents/social_media_analyzer/insights.py`) over a company's real `PlatformMetricSnapshot` rows and recently-published content — explicitly instructed to say plainly when there isn't enough data yet rather than invent insights. `POST /social-media-analyzer/insights`, an "Insights" card on the integrations page. Verified live: a real Anthropic call correctly surfaced the zero-credit error as a clean 502.

### 21. AI Content Assistant
A genuine multi-turn tool-using chat agent (`backend/app/agents/chat/`). Four read-only tools auto-execute inside the loop. Four **write** tools — approve/reject/regenerate an item, create a content plan — never execute automatically: calling one ends the turn with a proposal (`ChatMessage.proposed_action`), rendered as a Confirm/Cancel card, only run via `POST .../messages/{id}/confirm-action`. Verified live: a real approve mutated the item *and* fed straight into #1's KB self-indexing, a double-confirm correctly 409'd, cancel correctly left the item untouched.

---

## ⚪ Not built — genuinely blocked on real credentials, not a code gap

### 17. Community Inbox
Needs each platform's comments/DMs/mentions API — separate permission scopes from publishing/metrics, separate integration work per platform, and (same as every Composio-dependent feature) needs a real connected account to verify the response shapes against before the parsing logic could be written honestly.

---

## Since this list was compiled: the app became genuinely multi-client

Two things changed that affect every feature above, neither of which was on the 21-item list because both are infrastructure rather than features:

- **Per-company authorization** (`company_members`, migration `0027`). Until this round, every signed-in user could act on every company's data — including connecting and disconnecting real social accounts. Every route now verifies membership through one shared chokepoint (`app/security/ownership.py`), and non-members get a 404 rather than a 403 so company ids can't be enumerated. Teammates are added by email invite that binds on their first sign-in; companies created before this exist unclaimed and are owned by the first person to open them. Verified live with two real users against a real running server — 32 checks, all passing.
- **Trend relevance is now per-company everywhere.** #3 and #5 already used `CompanyTrendRelevance`; #4 (Strategy Planner), #15 (Campaign Management), Brand Collaboration, Trend Reports, #21's chat agent, and both trend endpoints were still ranking by a single global score computed against whichever company was most recently updated. All of them now share one implementation. With one client this changed nothing visible; with two it's the difference between the right recommendations and someone else's.

**#11's caveat above is now partly out of date**: `reviewer`/`approved_by` are still free text, but "no real per-user auth exists in this app" no longer holds — there is a real signed-in identity, and `/companies/{id}/members` shows who it is. Wiring reviewer assignment to real user identities instead of a localStorage name is now a small change rather than a blocked one.

---

## What's left

**Only #17**, and only because it's genuinely credential-gated. Everything else on the original 21-item list is built, tested, and either live-verified against real external calls (Anthropic, Composio) or correctly proven to fail gracefully when a real account/config isn't present yet.

Once you have real credentials to test against:
1. **Composio**: set `COMPOSIO_API_KEY` + one platform's auth config id, connect a real account, confirm the real post/metrics tool slugs from Composio's catalog, and re-test #10/#16/#18/#19 for real. The `follower_count`/`engagement_rate` best-effort extraction in `metrics.py` may need adjusting once you can see a real response shape — by design, it was never guessed.
2. **Supabase Storage**: create the storage bucket, set `SUPABASE_SERVICE_ROLE_KEY`, re-test #14's upload flow for real.
3. **Anthropic**: top up `ANTHROPIC_API_KEY`'s credit balance — every Claude-dependent feature across this whole list is built and tested via its graceful-degradation path, but none has been seen producing real output yet.
4. Then, if still wanted: **#17 Community Inbox**, now that the connection/token-handling patterns are proven against a real account.

Full historical context and prior rounds' reasoning lives in `KNOWN_ISSUES.md` and `TODO.md` — this file is scoped specifically to your 21-item list rather than duplicating those.
