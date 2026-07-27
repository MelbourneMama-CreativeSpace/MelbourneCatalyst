"""Per-platform Composio configuration — one dict entry per platform, so
adding a 7th platform later is a new entry, not new code paths.

Each platform maps to a Composio toolkit slug (confirmed against the real
`composio-client` package and composio.dev's toolkit catalog, not guessed)
and the `Settings` attribute holding that platform's Composio "auth config"
id — an id Composio issues after you create a `use_custom_auth` config in
its dashboard using that platform's own registered OAuth app credentials.
This app never sees those raw client id/secret values; it only holds the
resulting auth config id.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True, slots=True)
class PlatformComposioConfig:
    toolkit_slug: str
    auth_config_id_setting: str


PLATFORM_CONFIGS: dict[str, PlatformComposioConfig] = {
    "instagram": PlatformComposioConfig(
        toolkit_slug="instagram", auth_config_id_setting="COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID"
    ),
    "facebook": PlatformComposioConfig(
        toolkit_slug="facebook", auth_config_id_setting="COMPOSIO_FACEBOOK_AUTH_CONFIG_ID"
    ),
    "twitter": PlatformComposioConfig(
        toolkit_slug="twitter", auth_config_id_setting="COMPOSIO_TWITTER_AUTH_CONFIG_ID"
    ),
    "linkedin": PlatformComposioConfig(
        toolkit_slug="linkedin", auth_config_id_setting="COMPOSIO_LINKEDIN_AUTH_CONFIG_ID"
    ),
    "tiktok": PlatformComposioConfig(
        toolkit_slug="tiktok", auth_config_id_setting="COMPOSIO_TIKTOK_AUTH_CONFIG_ID"
    ),
    "youtube": PlatformComposioConfig(
        toolkit_slug="youtube", auth_config_id_setting="COMPOSIO_YOUTUBE_AUTH_CONFIG_ID"
    ),
}


def get_platform_config(platform: str) -> PlatformComposioConfig:
    try:
        return PLATFORM_CONFIGS[platform]
    except KeyError:
        raise ValueError(f"Unknown platform: {platform!r}") from None


def get_auth_config_id(platform: str) -> str:
    """Empty string if this platform's auth config hasn't been set up yet."""
    config = get_platform_config(platform)
    return getattr(settings, config.auth_config_id_setting)


def is_platform_configured(platform: str) -> bool:
    return bool(settings.COMPOSIO_API_KEY) and bool(get_auth_config_id(platform))
