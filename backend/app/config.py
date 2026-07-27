"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "MMCS Social Network"
    DEBUG: bool = True
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database (Supabase Postgres, asyncpg driver — e.g.
    # postgresql+asyncpg://postgres:<password>@<project>.supabase.co:5432/postgres)
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/mmcs"

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
    GOOGLE_TRENDS_SEED_KEYWORDS: list[str] = ["marketing", "social media", "AI"]
    # Reddit — read-only OAuth (a free "script" app registration), not the
    # public JSON endpoints (those return 403 Blocked in practice now).
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_SUBREDDITS: list[str] = ["marketing", "socialmedia", "smallbusiness"]
    RSS_FEED_URLS: list[str] = [
        "https://feeds.feedburner.com/TechCrunch",
        "https://www.socialmediatoday.com/feeds/news/",
    ]
    YOUTUBE_API_KEY: str = ""
    YOUTUBE_SEARCH_QUERIES: list[str] = ["marketing trends", "social media strategy"]

    # X / Twitter — API v2 recent search needs a paid developer tier
    TWITTER_BEARER_TOKEN: str = ""
    TWITTER_SEARCH_QUERIES: list[str] = ["marketing trends", "social media strategy"]

    # Instagram — Graph API hashtag search needs a Business/Creator account
    INSTAGRAM_ACCESS_TOKEN: str = ""
    INSTAGRAM_BUSINESS_ACCOUNT_ID: str = ""
    INSTAGRAM_HASHTAGS: list[str] = ["marketing", "socialmedia"]

    # TikTok — Research API needs academic/institutional approval
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    TIKTOK_SEARCH_KEYWORDS: list[str] = ["marketing trends", "social media"]

    # Knowledge Base — Voyage AI embeddings (voyage-3-lite is 1024-dim)
    VOYAGE_API_KEY: str = ""
    VOYAGE_MODEL: str = "voyage-3-lite"

    # Company Analyzer — onboarding crawl
    COMPANY_ONBOARDING_MAX_PAGES: int = 10

    # Content Management — Strategy Consultant + Content Planner
    STRATEGY_MAX_TRENDS: int = 10
    CONTENT_PLAN_MAX_TRENDS: int = 10
    CONTENT_PLAN_DAYS: int = 14

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

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
