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
    # Composio tool slug for this platform's "create a post" action (e.g.
    # "LINKEDIN_CREATE_LINKEDIN_POST"). Deliberately a *setting*, not a
    # hardcoded value here — unlike toolkit_slug (confirmed against the
    # real composio-client package), the exact per-action slug can't be
    # verified without a live Composio account and its tool catalog for
    # this toolkit. Guessing it would risk a silently-wrong integration
    # once real credentials exist; look it up in Composio's dashboard/
    # catalog once you have an account, same as the auth config id.
    post_tool_slug_setting: str
    # Same deal as post_tool_slug_setting, for whichever "get account/
    # post metrics" action this toolkit exposes (e.g. profile insights,
    # follower count) — left blank for the same reason.
    metrics_tool_slug_setting: str


PLATFORM_CONFIGS: dict[str, PlatformComposioConfig] = {
    "instagram": PlatformComposioConfig(
        toolkit_slug="instagram",
        auth_config_id_setting="COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID",
        post_tool_slug_setting="COMPOSIO_INSTAGRAM_POST_TOOL_SLUG",
        metrics_tool_slug_setting="COMPOSIO_INSTAGRAM_METRICS_TOOL_SLUG",
    ),
    "facebook": PlatformComposioConfig(
        toolkit_slug="facebook",
        auth_config_id_setting="COMPOSIO_FACEBOOK_AUTH_CONFIG_ID",
        post_tool_slug_setting="COMPOSIO_FACEBOOK_POST_TOOL_SLUG",
        metrics_tool_slug_setting="COMPOSIO_FACEBOOK_METRICS_TOOL_SLUG",
    ),
    "twitter": PlatformComposioConfig(
        toolkit_slug="twitter",
        auth_config_id_setting="COMPOSIO_TWITTER_AUTH_CONFIG_ID",
        post_tool_slug_setting="COMPOSIO_TWITTER_POST_TOOL_SLUG",
        metrics_tool_slug_setting="COMPOSIO_TWITTER_METRICS_TOOL_SLUG",
    ),
    "linkedin": PlatformComposioConfig(
        toolkit_slug="linkedin",
        auth_config_id_setting="COMPOSIO_LINKEDIN_AUTH_CONFIG_ID",
        post_tool_slug_setting="COMPOSIO_LINKEDIN_POST_TOOL_SLUG",
        metrics_tool_slug_setting="COMPOSIO_LINKEDIN_METRICS_TOOL_SLUG",
    ),
    "tiktok": PlatformComposioConfig(
        toolkit_slug="tiktok",
        auth_config_id_setting="COMPOSIO_TIKTOK_AUTH_CONFIG_ID",
        post_tool_slug_setting="COMPOSIO_TIKTOK_POST_TOOL_SLUG",
        metrics_tool_slug_setting="COMPOSIO_TIKTOK_METRICS_TOOL_SLUG",
    ),
    "youtube": PlatformComposioConfig(
        toolkit_slug="youtube",
        auth_config_id_setting="COMPOSIO_YOUTUBE_AUTH_CONFIG_ID",
        post_tool_slug_setting="COMPOSIO_YOUTUBE_POST_TOOL_SLUG",
        metrics_tool_slug_setting="COMPOSIO_YOUTUBE_METRICS_TOOL_SLUG",
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


def get_post_tool_slug(platform: str) -> str:
    """Empty string if this platform's post tool slug hasn't been set."""
    config = get_platform_config(platform)
    return getattr(settings, config.post_tool_slug_setting)


def is_platform_configured(platform: str) -> bool:
    return bool(settings.COMPOSIO_API_KEY) and bool(get_auth_config_id(platform))


def is_publishing_configured(platform: str) -> bool:
    return is_platform_configured(platform) and bool(get_post_tool_slug(platform))


def get_metrics_tool_slug(platform: str) -> str:
    """Empty string if this platform's metrics tool slug hasn't been set."""
    config = get_platform_config(platform)
    return getattr(settings, config.metrics_tool_slug_setting)


def is_metrics_configured(platform: str) -> bool:
    return is_platform_configured(platform) and bool(get_metrics_tool_slug(platform))
