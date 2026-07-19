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

    # Social Media Analyzer — Platform Integration (OAuth connections)
    # Base URL this backend is reachable at, used to build the OAuth
    # callback redirect_uri (must match what's registered on each
    # platform's app). Distinct from FRONTEND_BASE_URL below.
    APP_BASE_URL: str = "http://localhost:8000"
    # Where the browser gets redirected after a connection completes —
    # the frontend, not this backend.
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    # Fernet key (Fernet.generate_key()) — encrypts OAuth tokens at rest
    # and doubles as the HMAC signing key for OAuth `state` params (see
    # app/security/token_encryption.py, app/security/oauth_state.py).
    TOKEN_ENCRYPTION_KEY: str = ""
    # Meta app (covers both Instagram and Facebook — one Meta app, two
    # product surfaces) — https://developers.facebook.com/apps
    META_APP_CLIENT_ID: str = ""
    META_APP_CLIENT_SECRET: str = ""
    # X/Twitter OAuth2 app — distinct from TWITTER_BEARER_TOKEN above,
    # which is a separate app-level credential for the Trend Analyzer's
    # read-only search — https://developer.twitter.com/en/portal/dashboard
    TWITTER_OAUTH_CLIENT_ID: str = ""
    TWITTER_OAUTH_CLIENT_SECRET: str = ""
    # LinkedIn app — https://www.linkedin.com/developers/apps
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    # TikTok "Login Kit" app — distinct from TIKTOK_CLIENT_KEY/SECRET
    # above, which is the separate Research API used by the Trend
    # Analyzer — https://developers.tiktok.com/apps
    TIKTOK_OAUTH_CLIENT_KEY: str = ""
    TIKTOK_OAUTH_CLIENT_SECRET: str = ""
    # Google Cloud OAuth client (covers YouTube) —
    # https://console.cloud.google.com/apis/credentials
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""

    # Trend Analyzer — Trend Outputs (weekly report / insights / content opportunities)
    TREND_REPORT_MAX_TRENDS: int = 15
    TREND_REPORT_DEFAULT_PERIOD_DAYS: int = 7

    # Knowledge Base — Knowledge Manager (audit reports)
    KNOWLEDGE_AUDIT_MAX_DOCUMENTS: int = 30

    # Knowledge Base — document sources (blog indexer, uploads, dashboard)
    KB_BLOG_MAX_ARTICLES: int = 5
    KB_DOCUMENT_LIST_DEFAULT_LIMIT: int = 50
    KB_UPLOAD_MAX_BYTES: int = 5_000_000

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
