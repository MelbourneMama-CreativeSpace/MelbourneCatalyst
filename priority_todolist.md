# Priority TODO — Content Studio Finalization

This supersedes `TODO.md`'s phase ordering **for now**. `TODO.md` stays as
the full long-term roadmap; this file is the short list we're actually
working off, scoped to the founder's five asks (see
`content-studio-audit` artifact for the full analysis this is based on).
Everything here is about **Content Studio only** — Strategy Consultant,
Content Planner, Campaign Manager, Brand Collaboration, Analytics — the
other three modules (Company Analyzer, Trend Analyzer, Social Media
Analyzer) are already built and stay as-is, just not the focus.

Priority order below is the build order. Don't start P1 before P0 is
done — P0 is the founder's actual acceptance test; everything else is
downstream of clearing it.

---

## P0 — Clear the founder's MVP bar

*"Can the content agent draft a real post right now, or is it still just
a spec?"* Right now: still a spec. `ContentItem` has `title` +
`description` (a brief), no finished copy. This is the one gate
everything else waits on.

- [x] Add `draft_copy: str | None` to `ContentItem`
      ([backend/app/db/models.py](backend/app/db/models.py)) + a new
      Alembic migration (`0013`)
- [x] Extend `GeneratedContentItem`
      ([backend/app/agents/content_management/schemas.py](backend/app/agents/content_management/schemas.py))
      with `draft_copy`
- [x] Rewrite the `generate_content_plan` tool schema and prompt in
      [backend/app/agents/content_management/content_planner.py](backend/app/agents/content_management/content_planner.py)
      so Claude outputs finished, platform-appropriate copy per item —
      not "enough to brief a writer." Mirrors the pattern already proven
      in `collaboration.py`'s `outreach_template` field. Also added a
      standalone `regenerate_draft_copy` + `POST
      /content-items/{id}/regenerate-draft` for re-drafting a single item
      without regenerating the whole calendar.
- [x] Persist the new field in
      [backend/app/agents/content_management/content_plan_graph.py](backend/app/agents/content_management/content_plan_graph.py)
- [x] Add `draft_copy` to `ContentItemOut` in
      [backend/app/models/content_management.py](backend/app/models/content_management.py)
- [x] Frontend: add `draft_copy` to the `ContentItem` type in
      [frontend/src/lib/api.ts](frontend/src/lib/api.ts)
- [x] Frontend: show the draft in the calendar detail panel in
      [frontend/src/components/content-plan-view.tsx](frontend/src/components/content-plan-view.tsx) —
      copy-to-clipboard button + a "regenerate this item" action
- [x] Backend tests: agent-level (mocked Claude — asserts `draft_copy` is
      populated and non-empty on success, item skipped when Claude omits
      it), graph-level, API-level (17 new backend tests this round)
- [x] Full verification pass (see Definition of Done below) before
      moving to P1

## P1 — Name the product around the one task

*"He wants you to identify the one task the MMCS team dreads doing every
single week."* Recommendation from the audit: **drafting the actual
caption/copy for every slot in the weekly calendar** — highest
frequency, most mechanical, least loved, and exactly what P0 fixes.

- [ ] Confirm this is the right task with the founder — **still your call
      to make**, not something this round could resolve on its own. The
      copy changes below already assume this answer; revisit them if he
      picks a different candidate.
- [x] Proceeded with the recommended framing: adjusted the content plan
      page, strategy page's "Generate content plan" button (now "Draft
      this week's captions"), and the homepage's hero/messaging to frame
      the product as "this week's captions, drafted" rather than generic
      "content planning" —
      [frontend/src/components/content-plan-view.tsx](frontend/src/components/content-plan-view.tsx),
      [frontend/src/components/strategy-view.tsx](frontend/src/components/strategy-view.tsx),
      [frontend/src/app/page.tsx](frontend/src/app/page.tsx)

## P2 — Scope the live app to Content Studio only

Already true in the codebase (it's already its own module); this is
about what the MMCS team actually sees when they open the app day to
day.

- [x] Hid Company Analyzer's competitor research, Platform Integration,
      Trend Analyzer's reports, and the Knowledge Base panel behind a
      collapsed "Other modules" disclosure on the company page
      ([frontend/src/components/company-profile.tsx](frontend/src/components/company-profile.tsx))
      — routes still work, just not front and center. Homepage
      ([frontend/src/app/page.tsx](frontend/src/app/page.tsx)) now leads
      with "Open Content Studio" / "Add a client" instead of a 4-module
      grid, with the other modules listed as "still in development"
      links rather than glossy cards. Also removed the fabricated-feeling
      landing-page stats ("100+ Data Sources", "<1s Response Time" etc.)
      per finding #4 of the audit.
- [x] Confirmed: onboarding only needs the Company Analyzer's scrape +
      extract step (name, industry, target audience, niche keywords,
      brand voice, summary) — Strategy/Content Planner already only read
      those fields, nothing else from the other modules is required.
- [x] Decided: Trend Analyzer stays as an internal signal only. The
      "View matched trends" link was removed from the company page's
      primary actions; `/trends` is still reachable directly by URL but
      no longer linked from the daily workflow.

## P3 — Internal daily-use gaps

Two real gaps from the audit, both matter once this is actually used
daily across more than one client.

- [x] **Multi-tenant trend scoring** — added `CompanyTrendRelevance`
      (migration `0014`), a per-(company, trend) score computed for
      *every* complete company when a trend is first discovered, not just
      whichever one was "most recently updated." The Content Planner's
      trend context
      ([backend/app/agents/content_management/content_plan_graph.py](backend/app/agents/content_management/content_plan_graph.py))
      now prefers this per-company score, falling back to the legacy
      global `Trend.relevance_score` when a company has none yet (e.g.
      onboarded after the last collection run). **Scope note:** only the
      Content Planner was switched over this round — Strategy Consultant,
      Campaign Manager, Brand Collaboration, Trend Reports, and the
      `/trends`+`/recommended` endpoints still read the legacy global
      score. Migrating all of those in one pass without a real
      second-client scenario to verify against risked introducing subtle
      relevance-ranking regressions across every generation agent at
      once — left as a documented follow-up in `KNOWN_ISSUES.md` rather
      than guessed at.
- [x] **Basic user identity** — added `approved_by` (free-text, not real
      auth) to `Strategy` and `ContentItem`, set via a name field on the
      strategy and content-plan pages, remembered in `localStorage` so
      nobody retypes it per item. Shows as "Approved by X" / "Rejected by
      X" wherever the approval status is shown.
- [ ] (stretch, only after the above) a lightweight client switcher in
      the UI — not attempted this round; still just onboard-and-click-in
      per client on the companies list.

---

## Explicitly not doing right now

Per the founder's own steer — these are roadmap, not this round's work:

- Business Intelligence / Market Intelligence / Social Intelligence
  beyond what's already built (Company Analyzer, Trend Analyzer, Social
  Media Analyzer stay frozen as-is)
- Campaign Manager's real-time performance tracker, A/B testing,
  reports generator — needs live platform data
- Brand Collaboration's influencer discovery engine (named real
  accounts) + ROI predictor — needs live social search/data
- Analytics Engine (all 7 items) — needs live campaign/engagement data
- Anything else flagged credential-gated in `KNOWN_ISSUES.md`

Do not build fabricated placeholders for any of the above to make the
product look more complete — the founder's requirement #4 (no fabricated
data) applies to this list specifically. Leave it honestly unbuilt.

---

## Definition of done for this round

- [x] The pipeline end-to-end (schema → prompt → persistence → API →
      UI) is built and verified so that generating a calendar produces a
      `draft_copy` per item, not a brief — confirmed via mocked-Claude
      tests and a live-seeded DB. **Caveat:** this environment has no
      real `ANTHROPIC_API_KEY`, so the actual live Claude call producing
      real caption text has not been seen firsthand — same caveat as
      every prior round's generation work. That's the one thing you'll
      want to check yourself once a key is configured.
- [x] No fabricated numbers or mocked results introduced anywhere in
      this round's work — including the landing page, which previously
      had invented stats
- [x] Full verification pass: 338/338 backend tests passing, `npm run
      lint && npx tsc --noEmit && npm run build` clean, a live smoke test
      against a throwaway SQLite DB (seeded two companies to prove the
      multi-tenant trend fix), and a browser walkthrough of the homepage,
      company page, strategy page, and content calendar
- [x] `TODO.md` and `KNOWN_ISSUES.md` updated to reflect what actually
      shipped this round, same as every prior round
