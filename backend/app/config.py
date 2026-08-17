"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "LoomVerse AI"
    DEBUG: bool = True
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database (Supabase Postgres, asyncpg driver — e.g.
    # postgresql+asyncpg://postgres:<password>@<project>.supabase.co:5432/postgres)
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/mmcs"

    # Auth — Supabase Auth. The frontend talks to Supabase directly for
    # sign-in/sign-up; this backend only ever verifies the resulting JWT
    # on incoming requests. Supabase projects sign session tokens with
    # either a shared HS256 secret (SUPABASE_JWT_SECRET — Settings → API
    # → JWT Settings → "Legacy JWT Secret") or, on projects that have
    # opted into asymmetric signing keys, ES256 — verified against the
    # project's public JWKS endpoint instead, which only needs
    # SUPABASE_URL (no secret at all). See app/security/auth.py, which
    # checks each token's own `alg` header and verifies accordingly
    # rather than assuming one or the other.
    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""
    # Media & Asset Library — Supabase Storage. This is a DIFFERENT key
    # from the auth secret above: a server-side service-role key that
    # bypasses RLS, needed to upload/delete on the app's behalf. Never
    # exposed to the frontend. The bucket itself must be created once by
    # hand in Supabase's dashboard — this app doesn't auto-create it,
    # same "you register it once, we only hold the reference" pattern as
    # Composio's auth configs below.
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "media-library"
    MEDIA_UPLOAD_MAX_BYTES: int = 20_000_000

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI / LLM
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # LangSmith tracing for the LangGraph pipeline (optional — no-op if unset)
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""

    # Trend Analyzer
    TREND_COLLECTION_INTERVAL_HOURS: int = 6
    # ISO 3166-1 alpha-2 country code for the `explore` API's `geo` param
    # (e.g. "US", "AU"); "" means worldwide. Note: this is a different
    # format than the old trending_searches()'s `pn` param used (full
    # country names) — that method is no longer used (see google_trends.py).
    GOOGLE_TRENDS_REGION: str = ""
    # What each collector searches for is NOT configured here — it is
    # resolved at collection time from the onboarded companies' extracted
    # `niche_keywords` (see `trend_analyzer/niche.py`). These two only bound
    # how much of that resolved niche gets used per run, so adding companies
    # can't grow external API spend without limit.
    TREND_NICHE_MAX_KEYWORDS: int = 12
    # Deliberately far lower: Meta caps an Instagram account at 30 unique
    # hashtags per rolling 7 days, shared across every run in that window.
    TREND_NICHE_MAX_HASHTAGS: int = 5
    # Reddit — read-only OAuth (a free "script" app registration), not the
    # public JSON endpoints (those return 403 Blocked in practice now).
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    # How many subreddits to discover per niche keyword via Reddit's own
    # subreddit search — keywords like "handmade ceramics" are not subreddit
    # names, so they can't be used as one directly.
    REDDIT_SUBREDDITS_PER_KEYWORD: int = 2
    # Optional supplemental static feeds, still supported alongside the
    # dynamic per-niche-keyword Google News search RSSCollector now also
    # does — leave empty to rely on the dynamic feeds only.
    RSS_FEED_URLS: list[str] = []
    YOUTUBE_API_KEY: str = ""

    # X / Twitter — API v2 recent search needs a paid developer tier
    TWITTER_BEARER_TOKEN: str = ""

    # Instagram — Graph API hashtag search needs a Business/Creator account
    INSTAGRAM_ACCESS_TOKEN: str = ""
    INSTAGRAM_BUSINESS_ACCOUNT_ID: str = ""

    # TikTok — Research API needs academic/institutional approval
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""

    # Shared secret for the unauthenticated POST /internal/trend-collection
    # endpoint — lets an external scheduler (a GitHub Actions cron workflow,
    # see .github/workflows/trend-collection.yml) trigger a collection run
    # over plain HTTP, which has no way to hold a real user session. Leave
    # blank to disable the endpoint entirely (503s with an explanation).
    CRON_SECRET: str = ""

    # Knowledge Base — Voyage AI embeddings (voyage-3-lite is 1024-dim)
    VOYAGE_API_KEY: str = ""
    VOYAGE_MODEL: str = "voyage-3-lite"

    # Company Analyzer — onboarding crawl
    COMPANY_ONBOARDING_MAX_PAGES: int = 10

    # Content Management — Strategy Consultant + Content Planner
    STRATEGY_MAX_TRENDS: int = 10
    CONTENT_PLAN_MAX_TRENDS: int = 10
    CONTENT_PLAN_DAYS: int = 14
    # A single ad-hoc post (create_manual_item — the chat/manual-item-form
    # path) doesn't need as much ambient trend context as a whole
    # calendar does; smaller than CONTENT_PLAN_MAX_TRENDS on purpose.
    MANUAL_ITEM_MAX_TRENDS: int = 5

    # Content Management — Campaign Manager + Brand Collaboration
    COLLABORATION_MAX_IDEAS: int = 5

    # Social Media Analyzer — Platform Integration (OAuth connections),
    # brokered through Composio rather than this app doing raw OAuth
    # itself. Composio custodies tokens; this backend never sees them.
    #
    # Where the browser gets redirected after a connection completes —
    # the frontend, not this backend.
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    # https://app.composio.dev — account-level API key.
    COMPOSIO_API_KEY: str = ""
    # Each of these is an existing Composio "auth config" id (looks like
    # "ac_...") — created once via the Composio dashboard using
    # `use_custom_auth`, with that platform's own registered OAuth app
    # client ID/secret pasted in there (not here — the Composio SDK
    # version this app uses doesn't accept raw client credentials
    # programmatically, only via its dashboard UI). One Meta auth config
    # can cover both Instagram and Facebook if you registered one Meta
    # app for both; set the same id in both settings if so.
    COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID: str = ""
    COMPOSIO_FACEBOOK_AUTH_CONFIG_ID: str = ""
    COMPOSIO_TWITTER_AUTH_CONFIG_ID: str = ""
    COMPOSIO_LINKEDIN_AUTH_CONFIG_ID: str = ""
    COMPOSIO_TIKTOK_AUTH_CONFIG_ID: str = ""
    COMPOSIO_YOUTUBE_AUTH_CONFIG_ID: str = ""

    # Social Media Analyzer — Publishing. Each is the Composio *tool slug*
    # for that platform's "create a post" action (e.g.
    # "LINKEDIN_CREATE_LINKEDIN_POST") — look it up in Composio's tool
    # catalog for that toolkit once you have a real account; this app
    # doesn't guess it, since an exact action slug can't be verified
    # without live API access. Leave blank until you've confirmed it.
    COMPOSIO_INSTAGRAM_POST_TOOL_SLUG: str = ""
    COMPOSIO_FACEBOOK_POST_TOOL_SLUG: str = ""
    COMPOSIO_TWITTER_POST_TOOL_SLUG: str = ""
    COMPOSIO_LINKEDIN_POST_TOOL_SLUG: str = ""
    COMPOSIO_TIKTOK_POST_TOOL_SLUG: str = ""
    COMPOSIO_YOUTUBE_POST_TOOL_SLUG: str = ""
    # How often the scheduler checks for due scheduled posts.
    PUBLISH_SCHEDULER_INTERVAL_MINUTES: int = 5

    # Real YouTube video uploads (youtube_upload.py) are queued rather than
    # one-shot — a transient failure (a stalled network hop, a Composio
    # 5xx) retries automatically instead of just failing once. Capped so a
    # permanently-broken upload (bad config, a deleted video source)
    # doesn't retry forever.
    YOUTUBE_UPLOAD_SCHEDULER_INTERVAL_MINUTES: int = 15
    MAX_YOUTUBE_UPLOAD_ATTEMPTS: int = 5

    # Real per-post metrics (post_metrics.py) — the data layer under
    # LoomVerse's Analysis. Every run re-syncs every published item, so
    # this is deliberately not aggressive: matches trend collection's own
    # 6-hour cadence rather than something tighter that would risk
    # rate limits across every connected platform at once.
    POST_METRICS_SYNC_INTERVAL_MINUTES: int = 360

    # Same "you look it up in Composio's catalog, we don't guess it"
    # deal as the post tool slugs above, for whichever "get account/post
    # metrics" action each toolkit exposes.
    COMPOSIO_INSTAGRAM_METRICS_TOOL_SLUG: str = ""
    COMPOSIO_FACEBOOK_METRICS_TOOL_SLUG: str = ""
    COMPOSIO_TWITTER_METRICS_TOOL_SLUG: str = ""
    COMPOSIO_LINKEDIN_METRICS_TOOL_SLUG: str = ""
    COMPOSIO_TIKTOK_METRICS_TOOL_SLUG: str = ""
    COMPOSIO_YOUTUBE_METRICS_TOOL_SLUG: str = ""
    # How often the scheduler syncs metrics for every connected platform.
    METRICS_SYNC_INTERVAL_MINUTES: int = 360

    # Trend Analyzer — Trend Outputs (weekly report / insights / content
    # opportunities / campaign-history comparison / competitor-activity
    # correlation)
    TREND_REPORT_MAX_TRENDS: int = 15
    TREND_REPORT_DEFAULT_PERIOD_DAYS: int = 7
    TREND_REPORT_MAX_CAMPAIGNS: int = 5
    TREND_REPORT_MAX_COMPETITORS: int = 5

    # Trend Analyzer — recommended trends (formalizes the manual
    # min_relevance dashboard filter into an opinionated shortlist)
    TREND_RECOMMENDATION_MIN_RELEVANCE: float = 0.75
    TREND_RECOMMENDATION_MAX_AGE_DAYS: int = 7
    TREND_RECOMMENDATION_LIMIT: int = 10

    # Trend Analyzer — Content Opportunity Discovery
    OPPORTUNITY_MAX_TRENDS: int = 10
    OPPORTUNITY_SEASONAL_WINDOW_DAYS: int = 30

    # Trend Analyzer — scheduled daily trend report (period_days=1 report
    # auto-generated per complete company, same job pattern as kb_reindex)
    TREND_DAILY_REPORT_INTERVAL_HOURS: int = 24

    # Knowledge Base — Knowledge Manager (audit reports)
    KNOWLEDGE_AUDIT_MAX_DOCUMENTS: int = 30

    # Knowledge Base — document sources (blog indexer, uploads, dashboard)
    KB_BLOG_MAX_ARTICLES: int = 5
    KB_DOCUMENT_LIST_DEFAULT_LIMIT: int = 50
    KB_UPLOAD_MAX_BYTES: int = 5_000_000

    # Knowledge Base — scheduled re-index (automated indexing + incremental
    # updates). Daily by default — a company's own site changes far less
    # often than trending topics, so this is much less aggressive than
    # TREND_COLLECTION_INTERVAL_HOURS above.
    KB_REINDEX_INTERVAL_HOURS: int = 24

    # Intelligent Chat — tool-using conversational agent over the app's own
    # data. Non-streaming: a bounded iteration cap keeps a worst-case turn
    # (CHAT_MAX_ITERATIONS tool round-trips + one final forced-answer call)
    # comfortably within a normal HTTP request timeout.
    CHAT_MAX_ITERATIONS: int = 6
    CHAT_MAX_TOKENS: int = 4096

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Temporary pre-launch access gate — see require_allowlisted_user in
    # app/security/auth.py. Empty (the default) means unrestricted, i.e.
    # identical to today's behavior (any valid Supabase session). Once
    # populated, every /api/v1 route additionally requires the signed-in
    # user's email to appear here. Meant to be deleted entirely once
    # Stripe billing becomes the real access gate — same JSON-array-in-.env
    # format as CORS_ORIGINS, e.g. ALLOWED_USER_IDS=["you@example.com"].
    ALLOWED_USER_IDS: list[str] = []

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
