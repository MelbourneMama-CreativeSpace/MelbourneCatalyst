# 📋 MMCS Social Network — TODO

> A phased implementation checklist for the MMCS Social Network platform.
> Mark items with `[x]` as they are completed.

---

## Phase 1: Foundation & Infrastructure

### Project Setup
- [x] Initialize Git repository
- [x] Create README.md with architecture documentation
- [x] Create TODO.md (this file)
- [x] Set up frontend (Next.js 15 + TypeScript + shadcn/ui)
- [x] Set up backend (Python FastAPI)
- [ ] Configure CI/CD pipeline
- [x] Set up Docker containers (frontend, backend — no database container; Supabase is hosted/remote)
- [x] Configure environment variables & secrets management (`.env.example` covers Trend Analyzer config; still no secrets manager for production)

### Database & Storage
- [x] Set up PostgreSQL database (Supabase, connected via `DATABASE_URL`)
- [x] Design database schema (`trends`, `companies`, `documents`, `strategies`, `content_plans`/`content_items`, `campaigns`, `collaborations`/`collaboration_ideas`, `competitors`, `platform_connections`/`platform_metric_snapshots`, `trend_reports`, `knowledge_audit_reports` so far)
- [x] Create database migrations (Alembic, `backend/alembic/`)
- [ ] Set up vector database for Knowledge Base (e.g., Pinecone, Weaviate, or pgvector)
- [x] Implement database connection pooling (SQLAlchemy async engine, default pool)

### Authentication & Authorization
- [ ] Implement user authentication (JWT / OAuth)
- [ ] Set up role-based access control (RBAC)
- [ ] Create user registration & login flows
- [ ] Implement API key management for agents

### Shared Infrastructure
- [ ] Set up task queue (Celery + Redis) for async agent execution
- [ ] Implement WebSocket support for real-time updates
- [ ] Create logging & monitoring system
- [ ] Set up error tracking (e.g., Sentry)

---

## Phase 2: Shared Knowledge Base

### Knowledge Base Core
- [x] Design knowledge base schema (`documents` table with `pgvector`-backed `embedding` column, `companies` FK)
- [x] Implement document ingestion pipeline (Company Analyzer graph: scrape → chunk → embed → persist; plus a shared `ingest_raw_document` primitive reused by every other source below)
- [x] Create vector embedding generation (`voyage-3-lite` via `AsyncVoyageClient` wrapper, batching + graceful failure)
- [x] Implement semantic search & retrieval (`similarity_search` via pgvector cosine distance)
- [x] Build knowledge base CRUD API (`GET/POST/DELETE /api/v1/knowledge-base/documents` — list/preview, detail, delete, manual entry, upload, blog-index all live now)

### Data Sources Integration
- [x] Website content scraper (httpx + trafilatura main-content extraction; discovers /, /about, /services, /products, /team)
- [ ] Social media profile importer (still deferred — same OAuth/API-tier issues as trend collectors; the OAuth *connection* flow exists from Phase 6 but no data-fetching logic does)
- [x] Blog/article indexer (RSS-driven — `POST /documents/blog-index` — feedparser finds entries, each article page is scraped/extracted the same way the website scraper works; verified live against a real public RSS feed)
- [x] Product page parser (scraped pages whose URL matches product/pricing/shop paths are now tagged `source_type="product_page"` instead of generic `"website"`, so they're filterable/auditable separately — a real "specialized" distinction, not a new structured-extraction Claude pipeline, since hallucinated pricing data with no way to verify it would be worse than the honest raw text)
- [x] Business document uploader (PDF/DOCX/TXT/MD — `POST /documents/upload`, `pypdf`/`python-docx` for extraction; verified live with a real generated DOCX)

### Knowledge Base Management
- [x] Build knowledge base dashboard UI (`/knowledge-base/[companyId]` — search, document list with source-type filters, upload/manual-entry/blog-index forms, per-document delete, all wired to real endpoints)
- [x] Create data freshness indicators (`GET /freshness`, shipped in an earlier round — shown on both the company page and the new dashboard)
- [x] Implement automatic re-indexing (re-onboarding already rebuilt from scratch; every new source now dedups by `source_url` too — re-running blog indexing or re-uploading the same file replaces old chunks instead of accumulating duplicates, verified live by re-running blog indexing twice and confirming the document count didn't change. Content-hash-based *partial* diffing, i.e. skipping unchanged sources entirely, remains a stretch goal — out of scope here)
- [x] Add manual data entry interface (`POST /documents/manual` + a title/content form on the dashboard)
- [x] Build knowledge base search UI (the dashboard's search box wires up `searchKnowledgeBase()`, which existed in the API client but was never called from any component until now)

---

## Phase 3: Company Analyzer

### Business Analyst Agent
- [x] Implement company profile analysis (LangGraph pipeline + Claude tool-use extractor)
- [x] Build business model identification (extracted field on Company profile)
- [x] Create target audience profiling (extracted field)
- [x] Implement brand voice analysis (extracted field)
- [ ] Build products & services cataloging (not extracted as a distinct field yet; captured in scraped content + summary — dedicated extraction deferred)
- [x] Create market positioning assessment (extracted `unique_value_prop` + `summary` on the profile)
- [x] Build company onboarding wizard UI (`/onboarding` — URL-only for the MVP; full multi-step wizard deferred)
- [x] Create business analysis dashboard (`/companies/[id]` — extracted profile view with live status polling)

### Competitor Research Agent
- [x] Implement competitor discovery (manual URL entry; AI-assisted is Claude suggesting candidate *names* from training knowledge — no live search, so URLs still require manual lookup)
- [x] Build competitor profile scraper (reuses Company Analyzer's `discover_and_scrape` + `extract_company_profile` directly)
- [x] Create product & pricing comparison
- [x] Implement marketing strategy analysis
- [ ] Build social presence tracker (needs live follower/engagement counts from a connected platform — not attempted)
- [ ] Create customer engagement monitor (needs live review/social data — not attempted)
- [x] Implement competitive gap analysis
- [x] Build competitor dashboard UI (`/competitor/[id]`)
- [x] Create competitor comparison reports (the comparison generation is the report)

### Knowledge Manager
- [ ] Implement automated knowledge indexing
- [ ] Build incremental update pipeline
- [x] Create knowledge freshness scoring (`GET /api/v1/knowledge-base/freshness` — pure computation over `documents.created_at`, no Claude call needed; document count + last-ingested + staleness days, shown on the company page)
- [ ] Implement cross-reference linking (needs a well-defined linking model between documents/entities — not attempted)
- [ ] Build knowledge graph visualization (needs a graph UI this project doesn't have — not attempted)
- [x] Create knowledge audit reports (`KnowledgeAuditReport` — Claude-generated coverage summary, identified gaps, recommendations over a sample of the company's documents; `/knowledge-audit/[id]`)

---

## Phase 4: Trend Analyzer

### Trend Discovery
- [x] Integrate Google Trends API (via `pytrends-modern`'s `related_queries()`, no key required — verified live, real data flowing)
- [x] Build Reddit trending topics scraper (public JSON endpoints, no auth)
- [x] Implement YouTube trending analysis (YouTube Data API v3, needs `YOUTUBE_API_KEY`)
- [ ] Integrate LinkedIn trending topics (no public trends API exists outside approved Marketing Partners — not attempted, would require scraping)
- [x] Build X (Twitter) trends collector (X API v2 recent search; needs a paid `TWITTER_BEARER_TOKEN` — free tier can't search)
- [x] Implement TikTok trends analysis (TikTok Research API; needs `TIKTOK_CLIENT_KEY`/`SECRET` from an academic/institutional grant — most teams can't get access)
- [x] Add Instagram trends collector (Graph API hashtag search; needs `INSTAGRAM_ACCESS_TOKEN` + a Business/Creator account behind a Meta app) — not in the original checklist, added alongside X/TikTok
- [x] Create RSS feed aggregator
- [x] Build news website monitor (covered by the RSS/news feed aggregator above)
- [x] Implement industry blog tracker (covered by the RSS/news feed aggregator above)
- [x] Create unified trend feed (LangGraph pipeline → Supabase `trends` table → `GET /api/v1/trend-analyzer` → `/trends` dashboard) — now spans 7 sources: Google Trends, Reddit, RSS, YouTube, X/Twitter, Instagram, TikTok

### Trend Matching
- [x] Build niche relevance scoring algorithm (`score_relevance` node — cosine similarity between trend title and company niche_keywords embeddings)
- [ ] Implement campaign history comparison (needs Phase 5 campaign history; deferred)
- [x] Create customer interest matching (via niche_keywords; more sophisticated persona matching deferred)
- [ ] Build competitor activity correlation (needs Competitor Research Agent from Phase 3; deferred)
- [x] Implement trend priority ranking (`min_relevance` filter + relevance-badge sort in dashboard)
- [ ] Create trend recommendation engine (currently a filter; proactive recommendations deferred)
- [x] Build trend matching dashboard UI (relevance badge on `TrendCard`, `min_relevance` filter in `/trends`)

### Performance Discovery
- [ ] Implement content performance analyzer
- [ ] Build engagement pattern recognition
- [ ] Create format effectiveness scoring
- [ ] Implement success/failure pattern learning
- [ ] Build performance insights dashboard
- [ ] Create historical performance reports

### Trend Outputs
- [ ] Build daily trending topics feed (the `/trends` dashboard already covers this on-demand; a scheduled digest is deferred)
- [x] Create weekly market report generator (`TrendReport` — one Claude generation over the top-N relevance-scored trends from the last `period_days`, default 7; `POST /api/v1/trend-analyzer/reports`)
- [x] Implement industry insights summarizer (`summary` + `notable_trends_summary` fields on the same `TrendReport` generation)
- [x] Build content opportunity recommender (`content_opportunities` field on the same `TrendReport` generation)
- [ ] Create trend alerts & notifications (needs a delivery channel — email/webhook — that doesn't exist; not attempted)

---

## Phase 5: Content Management

### Strategy Consultant Agent
- [x] Implement marketing strategy generator
- [x] Build campaign direction planner
- [x] Create growth recommendation engine
- [x] Implement business suggestion generator
- [x] Build strategy dashboard UI
- [ ] Create strategy approval workflow

### Content Planner Agent
- [x] Build content calendar engine
- [x] Create daily post generator (every generated `ContentItem` is a single day's post — the calendar engine already produces day-granularity items)
- [x] Implement weekly schedule builder (content plan generation now accepts an optional `days` window — 7/14/30 presets in the UI — instead of a fixed 14-day plan)
- [x] Build monthly campaign planner (same `days` override, 30-day preset)
- [x] Create audience-interest-based planning (`audience_interest` field on each generated item — Claude ties ideas to the company's target audience/niche keywords)
- [x] Implement seasonal event integration (`seasonal_event` field — a small fixed-date lookup table of upcoming awareness/commercial dates is passed as generation context; movable holidays like Easter/Mother's Day deliberately excluded since there's no year-awareness to compute them correctly)
- [x] Build drag-and-drop calendar UI (`content-plan-view.tsx` — a real month-grid calendar, native HTML5 drag-and-drop to reschedule items between days via `PATCH /content-items/{id}`)
- [x] Create content preview & approval flow (`approval_status` — pending/approved/rejected — on each `ContentItem`, click-to-preview panel with Approve/Reject controls)

### Campaign Manager Agent
- [x] Implement campaign creation workflow (Claude-generated from company + strategy + content plan)
- [x] Build campaign scheduling system (start/end date, seeded from the content plan's date range when given)
- [ ] Create real-time performance tracker (needs live campaign results from a connected platform — not attempted)
- [x] Implement budget allocation optimizer (Claude-suggested budget split — a recommendation, not computed from real ad-spend data)
- [ ] Build progress monitoring dashboard (implies tracking real metrics over time; only static lifecycle stage exists, see below)
- [ ] Create campaign A/B testing framework (needs live traffic/results — not attempted)
- [x] Implement campaign lifecycle management (`draft`→`scheduled`→`active`→`completed`→`archived`, manually advanced via PATCH)
- [ ] Build campaign reports generator (nothing to report on without live results — not attempted)

### Brand Collaboration Agent
- [ ] Implement influencer discovery engine (adapted to collaborator *archetypes*, not named real accounts — no live social search available; see below)
- [x] Build content creator matching (collaborator archetype + partnership angle, Claude-generated)
- [x] Create brand partnership finder (partnership angle generation, same as above)
- [x] Implement outreach template generator (per-idea draft outreach message)
- [ ] Build collaboration ROI predictor (Claude gives a qualitative rationale/priority, not a computed prediction — no historical data to predict from)
- [x] Create collaboration management dashboard (`/collaboration/[id]` page)

### Analytics Agent
- [ ] Implement campaign success measurement
- [ ] Build engagement analytics pipeline
- [ ] Create reach & impressions tracking
- [ ] Implement conversion tracking
- [ ] Build audience growth analytics
- [ ] Create automated reporting
- [ ] Build analytics visualization dashboard

---

## Phase 6: Social Media Analyzer

### Platform Integration Agent
- [ ] Implement Facebook/Meta API integration (OAuth connection flow is live — see below; no data-fetching against the API yet)
- [ ] Implement Instagram API integration (same — connection only)
- [ ] Implement LinkedIn API integration (same — connection only)
- [ ] Implement X (Twitter) API integration (same — connection only)
- [ ] Implement TikTok API integration (same — connection only)
- [ ] Implement YouTube API integration (same — connection only)
- [x] Build platform connection management UI (`PlatformConnections` on the company page — 6 platforms, Connect/Disconnect)
- [x] Create OAuth flow for each platform (generic OAuth2 authorization-code flow, PKCE for X, signed state, encrypted token storage — scaffolded and gracefully "not configured" until a real app is registered on each platform's developer console; never tested against a real app in this environment)
- [ ] Implement data sync scheduling (needs a real per-platform data-fetching writer first, deliberately not built this round — see Performance Tracking below)

### Performance Tracking Agent
Storage schema exists (`PlatformMetricSnapshot`), but no items below are
implemented — deliberately deferred, since parsing each platform's real
analytics response shape can't be verified without a live connected
account (none exists in this environment). All redone once a real
connection is available to test against.
- [ ] Build engagement rate tracker
- [ ] Create follower growth monitor
- [ ] Implement impressions & reach tracker
- [ ] Build click-through rate analyzer
- [ ] Create campaign performance correlator
- [ ] Implement business growth indicators
- [ ] Build real-time performance dashboard

### Social Analytics Agent
Same deferral as Performance Tracking above — downstream of data this
environment can't yet produce.
- [ ] Implement audience demographics collector
- [ ] Build engagement pattern analyzer
- [ ] Create platform performance benchmarker
- [ ] Implement customer interaction tracker
- [ ] Build community growth analyzer
- [ ] Create detailed analytics reports
- [ ] Build analytics exploration UI

### Channel Intelligence Agent
- [ ] Implement cross-platform performance ranking
- [ ] Build optimal posting time calculator
- [ ] Create audience behavior analyzer
- [ ] Implement platform-specific trend detector
- [ ] Build opportunity forecaster
- [ ] Create unified channel intelligence dashboard

---

## Phase 7: Integration & Polish

### Cross-Module Integration
- [ ] Connect all agents to shared Knowledge Base
- [ ] Implement inter-agent communication protocol
- [ ] Build agent orchestration system
- [ ] Create unified API layer
- [ ] Implement end-to-end workflow automation

### Frontend Polish
- [ ] Build unified dashboard with all module views
- [ ] Implement responsive design for mobile
- [ ] Create dark/light theme toggle
- [ ] Build notification system UI
- [ ] Implement onboarding flow
- [ ] Create settings & preferences page
- [ ] Build help & documentation section

### Testing & Quality
- [ ] Write unit tests for all agents
- [ ] Write integration tests for API endpoints
- [ ] Write E2E tests for critical user flows
- [ ] Implement load testing
- [ ] Perform security audit
- [ ] Create API documentation (OpenAPI/Swagger)

### Deployment
- [ ] Set up production infrastructure
- [ ] Configure domain & SSL
- [ ] Deploy frontend to Vercel / CDN
- [ ] Deploy backend to cloud provider
- [ ] Set up production database
- [ ] Configure monitoring & alerting
- [ ] Create deployment documentation

---

## Phase 8: Future Expansion (Planned)

- [ ] SEO Intelligence Agent
- [ ] Lead Generation Agent
- [ ] Customer Sentiment Agent
- [ ] AI Video Generation Agent
- [ ] Email Marketing Agent
- [ ] Website Performance Agent
- [ ] CRM Intelligence Agent
- [ ] Sales Forecasting Agent
- [ ] Customer Support Agent
- [ ] ROI Prediction Agent

---

> **Last Updated:** July 2026 (Phase 2 Knowledge Base completion round)
