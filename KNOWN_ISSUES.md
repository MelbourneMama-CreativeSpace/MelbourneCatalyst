# Known Issues & Incomplete States

Audit compiled after adding the Competitor Research Agent (Phase 3) —
the last remaining non-credential-buildable agent, on top of a Phase 5
that's now fully built out (Strategy Consultant, Content Planner,
Campaign Manager, Brand Collaboration). Per your steer, credential-based
testing (a real `ANTHROPIC_API_KEY`, real social-platform credentials, a
real Postgres connection) is explicitly **not** attempted — you're
handling that yourself once implementation work is further along.
Everything below was verified either by automated tests or by live
requests against a throwaway SQLite database + running frontend/backend,
none of which need real external credentials — including, this round,
a real live scrape of a real website (no credentials needed for scraping
itself, only for the Claude analysis step on top of it). Current repo
state: branch `business-analyzer` (this round's work, plus the previous
two rounds', not yet committed as of writing this file).

**Backend tests: 178/178 passing (was 153 before this round). Frontend:
lint/typecheck/build all clean.**

---

## ✅ Resolved this round — Competitor Research Agent

Reuses two already-proven patterns end to end rather than inventing a
third: Company Analyzer's BackgroundTasks + polling shape for the
scrape (real wall-clock time), Content Management's synchronous one-shot
Claude call for the comparison.

- **Competitor onboarding**: `POST /competitor-research/competitors
  {company_id, url}` — reuses `discover_and_scrape`/`extract_company_profile`
  from `company_analyzer` *directly* (not duplicated), scraping a
  competitor's own website the same way a company's is. No chunk/embed
  step — competitor content isn't part of the target company's own
  searchable Knowledge Base. **Verified live against a real website**
  (`example.com`) — the scrape genuinely ran, real SSRF validation
  passed, real content extraction happened; it correctly landed on
  `complete_no_profile` since no `ANTHROPIC_API_KEY` is configured here,
  same honest degradation as company onboarding.
- **Comparison generation**: `POST /competitors/{id}/comparison` — 409s
  unless both the company and competitor are `status == "complete"`,
  else runs a Claude comparison call producing product/pricing
  comparison, marketing strategy analysis, competitive gaps, and
  strategic recommendations. Tracked via a separate `comparison_status`
  field on the same row, independent of the onboarding `status` — same
  two-independent-lifecycles-on-one-row pattern as `Campaign.status` vs
  `Campaign.lifecycle_stage` last round.
- **Competitor name suggestions**: `POST /competitor-research/suggestions
  {company_id}` — Claude suggests candidate competitor *names* from
  training knowledge, explicitly **not** a live discovery tool (no web
  access to find or verify real URLs). Shown in the UI with a clear
  caveat, not wired in as clickable/prefilled, to avoid implying it's
  more authoritative than it is.
- New page `/competitor/[id]` (profile + comparison, ships with
  `error.tsx`/`loading.tsx` from the start) and a `CompetitorList`
  component on the company page (list + add-by-URL form + suggestions
  button).
- New table `competitors` via migration `0006_competitor_research.py`.

**Explicitly not attempted** — need live platform data that doesn't
exist here:
- Social presence tracker (needs live follower/engagement counts).
- Customer engagement monitor (needs live review/social data).

7 of 9 `TODO.md` checklist items delivered honestly; 2 correctly left
unbuilt rather than faked. See `TODO.md` for the itemized breakdown.

### A real bug caught by the test suite, not by review

While adding the `Competitor` model to `backend/app/db/models.py`, an
`Edit` call inserted the new class in the wrong place — splitting the
existing `CollaborationIdea` class in half, so its
`collaboration: Mapped[Collaboration] = relationship(...)` line ended up
indented under `Competitor` instead. This broke SQLAlchemy mapper
configuration for the *entire app* (every model, not just the new one)
with `Mapper 'CollaborationIdea' has no property 'collaboration'`.
Running the full test suite immediately after the change (rather than
just the new tests) caught it in seconds — 86 of 178 tests failed across
completely unrelated files, which was the tell. Fixed by moving the
relationship line back into `CollaborationIdea`. Worth remembering:
always re-run the *full* suite after any edit to a shared file like
`models.py`, not just the tests for what you just added.

### Click-tool verification gap from last round: effectively resolved

Last round's `KNOWN_ISSUES.md` flagged that the Browser pane's click
tool broke mid-session, leaving the Campaign lifecycle-stage buttons
un-click-verified. This round, the same tool worked normally — real
coordinates, successful clicks — and was used to genuinely drive the
"Add competitor" form (typed a URL, clicked submit, confirmed via the
API that a real competitor row was created and onboarding kicked off).
That's the identical `<form>`+`onClick`+`fetch` pattern the Campaign
lifecycle buttons use, so this stands as strong indirect confirmation
the earlier gap was a transient tooling hiccup, not a code issue — but a
direct click-through of the Campaign page next time you're at a keyboard
is still the fully certain way to close it out.

## ✅ Resolved previous round — Campaign Manager + Brand Collaboration

Both agents scoped to what's real without live platform data. Campaign
Manager: creation, budget suggestions, timeline (seeded from a content
plan's date range when given), and a manually-advanced
`lifecycle_stage`. Brand Collaboration: partnership ideation as
collaborator *archetypes* (not named real accounts), outreach templates,
qualitative priority. Not attempted: real-time performance tracking,
A/B testing, live influencer discovery, quantitative ROI prediction —
all need live platform/historical data. New tables via
`0005_campaign_collaboration.py`.

## ✅ Resolved earlier rounds — bug fixes + hardening (carried forward for context)

Cross-company data leaks fixed (strategy/content-plan/campaign/
collaboration/competitor cross-references now all validate they belong
to the same company), a malformed-Claude-item crash fixed (full item
construction wrapped in `try/except`, reused in every list-generating
agent since), a company-readiness guard added (`_get_ready_company_or_error`,
409s instead of generating from an empty profile), `error.tsx`/`loading.tsx`
boundaries on every detail route, a "past X" history section, a batch
trend-lookup endpoint. Plus the original hardening rounds: SSRF
protection, stray test artifacts, document accumulation on
re-onboarding, URL normalization, dead `numpy` dependency, Reddit's
PRAW/OAuth rewrite, `complete_no_profile` status, Google Trends
`related_queries()` rewrite.

---

## 🔴 Remaining: deferred by your explicit choice, not blocked

### No auth on any endpoint
Still true, now including the 4 new competitor-research routes. Fine for
local dev; **must** land before any non-local deployment. Recommendation
unchanged: Supabase Auth — also fixes the single-tenant Trend Matching
limitation below.

### Migration `0006_competitor_research.py` (and `0002`–`0005`) still untested against real Postgres
Now five migrations deep, all verified only against SQLite via
`Base.metadata.create_all()`, which bypasses Alembic entirely.

### No agent's Claude call has run against a real `ANTHROPIC_API_KEY`
Same caveat as the last two rounds, now covering Competitor Research
too. This round did verify a real, live, credential-free *website
scrape* end-to-end (see above) — the part that's specifically gated is
the Claude analysis layered on top.

---

## 🟡 Remaining: needs a product/design decision, not just a fix

- **Single-tenant assumption in Trend Matching** (unchanged) —
  `score_relevance` scores trends against "the most recently updated
  `complete` Company." Every agent that reads trends inherits this.
  Real fix is multi-tenancy tied to auth.

---

## 🟡 External-source fragility (verified live in prior rounds — not code bugs, unchanged, credential-gated)

- **YouTube, X/Twitter, Instagram, TikTok** collectors have never been
  tested against live credentials.
- **Reddit** uses PRAW/OAuth but has likewise never been tested against a
  real Reddit app registration — only mocked.
- **RSS and Google Trends** are the only two trend sources confirmed
  returning real data end-to-end, live — though as of this round, the
  Company Analyzer/Competitor Research *website scraper* is also
  confirmed working live against a real site (`example.com`), separate
  from the trend collectors.

---

## ⚪ Incomplete / deferred features (by design — see TODO.md for full detail)

Every agent that's genuinely buildable without external credentials is
now built: all of Phase 5 (Content Management) and Competitor Research
in Phase 3. What's left unbuilt is, almost without exception, gated on
either credentials (social platform APIs, a real Anthropic/Postgres
connection) or a product decision this session was told to defer (auth).
The remaining Phase 3 items (Knowledge Manager Agent, products/services
cataloging as a distinct field) are smaller and lower-value than what's
shipped; Phase 4's Trend Outputs (report generator, insights summarizer)
are Claude-based and technically non-credential, but thinner value adds
on an already-complete Trend Analyzer. See `TODO.md` for the full
phase-by-phase checklist.

---

## Priority list for next round

1. Non-credential feature work is now genuinely exhausted for the
   highest-value items — every agent with a real non-credential slice
   has one. Remaining non-credential candidates are smaller: Phase 4's
   Trend Outputs (weekly report generator, insights summarizer — both
   just another Claude-tool-use call over already-collected trend data),
   or Phase 3's Knowledge Manager Agent (thinner scope, overlaps with
   what the Knowledge Base already does implicitly).
2. When you're ready for credential-based testing: a real
   `ANTHROPIC_API_KEY` (biggest unknown — no agent's actual output
   quality has been seen yet), a Postgres connection string for
   `alembic upgrade head` (5 migrations deep now), and credentials for
   at least one of YouTube/X/Instagram/TikTok/Reddit.
3. A 30-second manual click-through of the Campaign lifecycle-stage
   buttons, for full certainty on the one gap noted above (low priority
   — strong indirect evidence it already works).
