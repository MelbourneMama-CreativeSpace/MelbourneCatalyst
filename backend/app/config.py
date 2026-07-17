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
    GOOGLE_TRENDS_REGION: str = "united_states"
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

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
