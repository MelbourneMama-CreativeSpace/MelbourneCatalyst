"""Public social-profile lookups by username — for "paste a handle and
build content inspired by it" requests, distinct from this app's own
connected accounts (see oauth_flow.py/publish.py for those).

Every platform's real capability was checked live against Composio's
actual toolkit (`client.tools.retrieve`) before writing any of this, not
assumed uniform. Only Twitter/X and YouTube genuinely support looking up
an ARBITRARY public account by username/handle:

- Twitter/X (`TWITTER_USER_LOOKUP_BY_USERNAME`): works for any public
  username, confirmed from its own schema ("Fetches public profile
  information for a valid and existing Twitter user by their username").
- YouTube (`YOUTUBE_GET_CHANNEL_ID_BY_HANDLE` / `YOUTUBE_LIST_CHANNELS`):
  works for any public handle via the `forHandle` filter.
- Facebook (`FACEBOOK_GET_PAGE_DETAILS`) is best-effort: Graph API
  generally accepts a Page's vanity username interchangeably with its
  numeric id for public node lookups, but — unlike the two above — this
  isn't separately confirmed against a live connected account, so a
  failure here is treated as "couldn't find it," never surfaced as
  working when it might not be.
- Instagram, LinkedIn, and TikTok explicitly do NOT support this, per
  each tool's own schema description, not assumed:
  - Instagram (`INSTAGRAM_GET_USER_INFO`): "Arbitrary public accounts
    cannot be queried" — only Business/Creator accounts you manage.
  - LinkedIn (`LINKEDIN_GET_PERSON`) needs a `person_id` that's "unique
    to the context of your application only" — not derivable from a
    public username at all. `LINKEDIN_GET_COMPANY_INFO` only returns
    organizations the authenticated user already administers.
  - TikTok (`TIKTOK_QUERY_CREATOR_INFO`) takes no parameters whatsoever
    — it can only ever return the connected account's own info.
  These three are deliberately excluded from `SUPPORTED_PLATFORMS` rather
  than attempted and silently failing.

A public lookup still runs through a real connected account's Composio
auth — there's no such thing as an unauthenticated call — so this always
needs *some* company's own connection for that platform, even though the
account actually being looked up is someone else's entirely.

Beyond the profile itself, `fetch_recent_posts` pulls a handful of an
account's actual recent posts/videos — a bio says what an account
*claims* to be about, real recent posts are what it's actually posting,
which is a much stronger signal for understanding its real niche/trends.
Same three platforms, same real-capability verification, same "empty is
an honest answer, never fabricated" contract. One genuine platform quirk
worth knowing: Twitter's `TWITTER_RECENT_SEARCH` only covers the last 7
days — an account with no matches there isn't necessarily inactive, it
just hasn't posted in that window.
"""

from __future__ import annotations

import asyncio
import logging
import re

from composio_client import Composio

from app.config import settings
from app.db.models import PlatformConnection

logger = logging.getLogger(__name__)

# Confirmed live against Composio's toolkit (see module docstring) —
# deliberately excludes instagram/linkedin/tiktok, which genuinely cannot
# look up an arbitrary public account.
SUPPORTED_PLATFORMS = ("twitter", "youtube", "facebook")

_PROFILE_URL_RE = re.compile(
    r"(?:twitter\.com|x\.com|youtube\.com|facebook\.com|fb\.com)/(@?[\w.\-]+)", re.I
)


def _client() -> Composio:
    return Composio(api_key=settings.COMPOSIO_API_KEY)


def _clean_handle(username: str) -> str:
    """Accepts a bare handle, one with a leading '@', or a full profile
    URL, and normalizes to a bare handle either way — a person pasting a
    username in chat is just as likely to paste the URL they were looking
    at."""
    username = username.strip()
    url_match = _PROFILE_URL_RE.search(username)
    if url_match:
        username = url_match.group(1)
    return username.lstrip("@")


async def fetch_twitter_profile(connection: PlatformConnection, username: str) -> dict | None:
    client = _client()
    handle = _clean_handle(username)

    def _execute():
        return client.tools.execute(
            "TWITTER_USER_LOOKUP_BY_USERNAME",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            # description/public_metrics/location aren't returned unless
            # explicitly requested — confirmed from the tool's own schema.
            arguments={"username": handle, "user_fields": ["description", "public_metrics", "location"]},
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None) or {}
    user = data.get("data") if isinstance(data, dict) else None
    if not isinstance(user, dict):
        return None
    metrics = user.get("public_metrics") or {}
    return {
        "platform": "twitter",
        "name": user.get("name"),
        "handle": user.get("username"),
        "bio": user.get("description"),
        "followers": metrics.get("followers_count"),
        "location": user.get("location"),
        "url": f"https://x.com/{user['username']}" if user.get("username") else None,
    }


async def fetch_youtube_profile(connection: PlatformConnection, handle: str) -> dict | None:
    client = _client()
    cleaned = _clean_handle(handle)

    def _execute():
        return client.tools.execute(
            "YOUTUBE_LIST_CHANNELS",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={"forHandle": cleaned, "part": "snippet,statistics"},
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None) or {}
    items = data.get("items") if isinstance(data, dict) else None
    if not items:
        return None
    channel = items[0]
    snippet = channel.get("snippet") or {}
    stats = channel.get("statistics") or {}
    custom_url = snippet.get("customUrl")
    return {
        "platform": "youtube",
        "name": snippet.get("title"),
        "handle": custom_url,
        "bio": snippet.get("description"),
        "followers": stats.get("subscriberCount"),
        "location": snippet.get("country"),
        "url": f"https://youtube.com/{custom_url}" if custom_url else None,
    }


async def fetch_facebook_profile(connection: PlatformConnection, username: str) -> dict | None:
    """Best-effort — see module docstring for why this one isn't as
    firmly confirmed as the Twitter/YouTube fetchers above."""
    client = _client()
    cleaned = _clean_handle(username)

    def _execute():
        return client.tools.execute(
            "FACEBOOK_GET_PAGE_DETAILS",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={
                "page_id": cleaned,
                "fields": "id,name,about,category,description,fan_count,followers_count,link",
            },
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None) or {}
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return {
        "platform": "facebook",
        "name": data.get("name"),
        "handle": cleaned,
        "bio": data.get("about") or data.get("description"),
        "followers": data.get("followers_count") or data.get("fan_count"),
        "location": None,
        "url": data.get("link"),
    }


_FETCHER_BY_PLATFORM = {
    "twitter": fetch_twitter_profile,
    "youtube": fetch_youtube_profile,
    "facebook": fetch_facebook_profile,
}


async def fetch_public_profile(
    platform: str, connection: PlatformConnection, username: str
) -> dict | None:
    """Never raises — returns None on any failure (not found, API error,
    or a platform outside SUPPORTED_PLATFORMS)."""
    fetcher = _FETCHER_BY_PLATFORM.get(platform)
    if fetcher is None:
        return None
    try:
        return await fetcher(connection, username)
    except Exception:
        logger.exception("Profile lookup failed for %s/%r", platform, username)
        return None


# --- Recent posts — a real signal for niche/topic/trend understanding, ----
# not just the bio. Same three supported platforms, same "never fabricate,
# empty is a valid honest answer" contract.


async def fetch_twitter_recent_posts(
    connection: PlatformConnection, handle: str, *, limit: int = 10
) -> list[dict]:
    """Recent Search only covers the last 7 days — a real API limitation,
    not a bug here. An account that hasn't posted in a week returns an
    empty list even though it clearly has a real posting history; callers
    should treat that as "nothing recent," never as "this account posts
    nothing.\""""
    client = _client()
    cleaned = _clean_handle(handle)

    def _execute():
        return client.tools.execute(
            "TWITTER_RECENT_SEARCH",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={
                "query": f"from:{cleaned} -is:retweet -is:reply",
                # API enforces a minimum of 10 regardless of what's asked for.
                "max_results": max(10, min(limit, 100)),
                # "text" is already returned by default — requesting it
                # again is explicitly documented as unnecessary.
                "tweet_fields": ["created_at", "public_metrics"],
            },
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None) or {}
    tweets = data.get("data") if isinstance(data, dict) else None
    if not isinstance(tweets, list):
        return []
    posts = []
    for tweet in tweets[:limit]:
        if not isinstance(tweet, dict):
            continue
        metrics = tweet.get("public_metrics") or {}
        posts.append(
            {
                "text": tweet.get("text"),
                "created_at": tweet.get("created_at"),
                "likes": metrics.get("like_count"),
                "reposts": metrics.get("retweet_count"),
            }
        )
    return posts


async def fetch_youtube_recent_videos(
    connection: PlatformConnection, channel_handle: str, *, limit: int = 10
) -> list[dict]:
    client = _client()

    def _execute():
        return client.tools.execute(
            "YOUTUBE_LIST_CHANNEL_VIDEOS",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            # channelId genuinely accepts a handle directly (incl. the
            # leading '@'), confirmed from the tool's own schema examples
            # — no separate channel-id resolution call needed here.
            arguments={"channelId": channel_handle, "maxResults": limit},
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None) or {}
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    videos = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        snippet = item.get("snippet") or {}
        videos.append(
            {
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "published_at": snippet.get("publishedAt"),
            }
        )
    return videos


async def fetch_facebook_recent_posts(
    connection: PlatformConnection, page_id: str, *, limit: int = 10
) -> list[dict]:
    client = _client()
    cleaned = _clean_handle(page_id)

    def _execute():
        return client.tools.execute(
            "FACEBOOK_GET_PAGE_POSTS",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={
                "page_id": cleaned,
                "limit": limit,
                "fields": "id,message,created_time,permalink_url",
            },
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None) or {}
    posts_raw = data.get("data") if isinstance(data, dict) else None
    if not isinstance(posts_raw, list):
        return []
    posts = []
    for post in posts_raw[:limit]:
        if not isinstance(post, dict):
            continue
        posts.append(
            {
                "text": post.get("message"),
                "created_at": post.get("created_time"),
                "url": post.get("permalink_url"),
            }
        )
    return posts


_RECENT_POSTS_FETCHER_BY_PLATFORM = {
    "twitter": fetch_twitter_recent_posts,
    "youtube": fetch_youtube_recent_videos,
    "facebook": fetch_facebook_recent_posts,
}


async def fetch_recent_posts(
    platform: str, connection: PlatformConnection, username: str, *, limit: int = 10
) -> list[dict]:
    """Never raises — returns [] on any failure, including a platform
    outside SUPPORTED_PLATFORMS or an account with nothing recent."""
    fetcher = _RECENT_POSTS_FETCHER_BY_PLATFORM.get(platform)
    if fetcher is None:
        return []
    try:
        return await fetcher(connection, username, limit=limit)
    except Exception:
        logger.exception("Recent-posts lookup failed for %s/%r", platform, username)
        return []
