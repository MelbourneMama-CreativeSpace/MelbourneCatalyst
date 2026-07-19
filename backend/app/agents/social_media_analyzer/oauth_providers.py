"""Per-platform OAuth2 configuration — one dict entry per platform, so
adding a 6th platform later is a new entry, not new code paths.

Authorize/token URLs and scopes are drawn from each platform's public
OAuth2 documentation as of this writing (Meta Graph API, X API v2 OAuth
2.0, LinkedIn OAuth 2.0, TikTok Login Kit, Google OAuth 2.0). These are
correct against the documented API shape but — like the rest of this
round — unverified against a real registered app, since none exists in
this environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import settings


@dataclass(frozen=True, slots=True)
class PlatformOAuthConfig:
    authorize_url: str
    token_url: str
    scopes: list[str] = field(default_factory=list)
    client_id_setting: str = ""
    client_secret_setting: str = ""
    # X's OAuth 2.0 requires PKCE (code_challenge/code_verifier) even for
    # confidential clients; the others don't.
    pkce: bool = False


PLATFORM_CONFIGS: dict[str, PlatformOAuthConfig] = {
    "instagram": PlatformOAuthConfig(
        authorize_url="https://www.facebook.com/v21.0/dialog/oauth",
        token_url="https://graph.facebook.com/v21.0/oauth/access_token",
        scopes=["instagram_basic", "instagram_manage_insights", "pages_show_list"],
        client_id_setting="META_APP_CLIENT_ID",
        client_secret_setting="META_APP_CLIENT_SECRET",
    ),
    "facebook": PlatformOAuthConfig(
        authorize_url="https://www.facebook.com/v21.0/dialog/oauth",
        token_url="https://graph.facebook.com/v21.0/oauth/access_token",
        scopes=["pages_show_list", "pages_read_engagement"],
        client_id_setting="META_APP_CLIENT_ID",
        client_secret_setting="META_APP_CLIENT_SECRET",
    ),
    "twitter": PlatformOAuthConfig(
        authorize_url="https://twitter.com/i/oauth2/authorize",
        token_url="https://api.twitter.com/2/oauth2/token",
        scopes=["tweet.read", "users.read", "offline.access"],
        client_id_setting="TWITTER_OAUTH_CLIENT_ID",
        client_secret_setting="TWITTER_OAUTH_CLIENT_SECRET",
        pkce=True,
    ),
    "linkedin": PlatformOAuthConfig(
        authorize_url="https://www.linkedin.com/oauth/v2/authorization",
        token_url="https://www.linkedin.com/oauth/v2/accessToken",
        scopes=["r_organization_social", "rw_organization_admin"],
        client_id_setting="LINKEDIN_CLIENT_ID",
        client_secret_setting="LINKEDIN_CLIENT_SECRET",
    ),
    "tiktok": PlatformOAuthConfig(
        authorize_url="https://www.tiktok.com/v2/auth/authorize",
        token_url="https://open.tiktokapis.com/v2/oauth/token/",
        scopes=["user.info.basic", "video.list"],
        client_id_setting="TIKTOK_OAUTH_CLIENT_KEY",
        client_secret_setting="TIKTOK_OAUTH_CLIENT_SECRET",
    ),
    "youtube": PlatformOAuthConfig(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        client_id_setting="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_setting="GOOGLE_OAUTH_CLIENT_SECRET",
    ),
}


def get_platform_config(platform: str) -> PlatformOAuthConfig:
    try:
        return PLATFORM_CONFIGS[platform]
    except KeyError:
        raise ValueError(f"Unknown platform: {platform!r}") from None


def get_client_credentials(platform: str) -> tuple[str, str]:
    """Returns (client_id, client_secret) — either may be empty if unset."""
    config = get_platform_config(platform)
    client_id = getattr(settings, config.client_id_setting)
    client_secret = getattr(settings, config.client_secret_setting)
    return client_id, client_secret


def is_platform_configured(platform: str) -> bool:
    client_id, client_secret = get_client_credentials(platform)
    return bool(client_id and client_secret)
