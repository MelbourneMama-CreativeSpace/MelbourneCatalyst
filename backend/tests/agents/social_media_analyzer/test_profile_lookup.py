"""Tests for public social-profile lookups by username (profile_lookup.py)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.agents.social_media_analyzer import profile_lookup


def _connection(platform: str, **overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        platform=platform,
        composio_connected_account_id="conn-123",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _clean_handle -----------------------------------------------------


def test_clean_handle_strips_leading_at():
    assert profile_lookup._clean_handle("@elonmusk") == "elonmusk"


def test_clean_handle_leaves_bare_handle_alone():
    assert profile_lookup._clean_handle("elonmusk") == "elonmusk"


def test_clean_handle_extracts_from_twitter_url():
    assert profile_lookup._clean_handle("https://twitter.com/elonmusk") == "elonmusk"
    assert profile_lookup._clean_handle("https://x.com/elonmusk") == "elonmusk"


def test_clean_handle_extracts_from_youtube_url():
    assert profile_lookup._clean_handle("https://www.youtube.com/@MrBeast") == "MrBeast"


def test_clean_handle_extracts_from_facebook_url():
    assert profile_lookup._clean_handle("https://facebook.com/nike") == "nike"


# --- fetch_twitter_profile ----------------------------------------------


async def test_fetch_twitter_profile_parses_the_real_response_shape(monkeypatch):
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(
                data={
                    "data": {
                        "id": "12345",
                        "name": "Elon Musk",
                        "username": "elonmusk",
                        "description": "Mars, cars, chips that talk to your brain",
                        "location": "Austin, TX",
                        "public_metrics": {
                            "followers_count": 200000000,
                            "following_count": 500,
                            "tweet_count": 40000,
                        },
                    }
                }
            )

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_twitter_profile(_connection("twitter"), "@elonmusk")

    assert result == {
        "platform": "twitter",
        "name": "Elon Musk",
        "handle": "elonmusk",
        "bio": "Mars, cars, chips that talk to your brain",
        "followers": 200000000,
        "location": "Austin, TX",
        "url": "https://x.com/elonmusk",
    }
    tool_slug, kwargs = calls[0]
    assert tool_slug == "TWITTER_USER_LOOKUP_BY_USERNAME"
    # The leading '@' must be stripped before hitting the real API — it
    # rejects usernames that still have one.
    assert kwargs["arguments"]["username"] == "elonmusk"
    assert kwargs["connected_account_id"] == "conn-123"


async def test_fetch_twitter_profile_returns_none_for_a_nonexistent_user(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={"errors": [{"title": "Not Found Error"}]})

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_twitter_profile(_connection("twitter"), "definitely_not_a_real_user_xyz")

    assert result is None


# --- fetch_youtube_profile -----------------------------------------------


async def test_fetch_youtube_profile_parses_the_real_response_shape(monkeypatch):
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(
                data={
                    "items": [
                        {
                            "snippet": {
                                "title": "MrBeast",
                                "description": "I make videos.",
                                "customUrl": "@MrBeast",
                                "country": "US",
                            },
                            "statistics": {
                                "subscriberCount": "300000000",
                                "videoCount": "800",
                                "viewCount": "50000000000",
                            },
                        }
                    ]
                }
            )

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_youtube_profile(_connection("youtube"), "MrBeast")

    assert result == {
        "platform": "youtube",
        "name": "MrBeast",
        "handle": "@MrBeast",
        "bio": "I make videos.",
        "followers": "300000000",
        "location": "US",
        "url": "https://youtube.com/@MrBeast",
    }
    tool_slug, kwargs = calls[0]
    assert tool_slug == "YOUTUBE_LIST_CHANNELS"
    assert kwargs["arguments"]["forHandle"] == "MrBeast"


async def test_fetch_youtube_profile_returns_none_when_no_channel_matches(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={"items": []})

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_youtube_profile(_connection("youtube"), "not_a_real_channel_xyz")

    assert result is None


# --- fetch_facebook_profile (best-effort) --------------------------------


async def test_fetch_facebook_profile_parses_the_real_response_shape(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(
                data={
                    "id": "123456",
                    "name": "Nike",
                    "about": "Just Do It.",
                    "followers_count": 40000000,
                    "link": "https://facebook.com/nike",
                }
            )

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_facebook_profile(_connection("facebook"), "nike")

    assert result["platform"] == "facebook"
    assert result["name"] == "Nike"
    assert result["bio"] == "Just Do It."
    assert result["followers"] == 40000000


async def test_fetch_facebook_profile_returns_none_without_a_real_id(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={})

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_facebook_profile(_connection("facebook"), "not_a_real_page")

    assert result is None


# --- fetch_public_profile (dispatcher) -----------------------------------


async def test_fetch_public_profile_dispatches_by_platform(monkeypatch):
    async def fake_youtube(connection, username):
        return {"platform": "youtube", "name": "fake"}

    monkeypatch.setitem(profile_lookup._FETCHER_BY_PLATFORM, "youtube", fake_youtube)

    result = await profile_lookup.fetch_public_profile("youtube", _connection("youtube"), "someone")

    assert result == {"platform": "youtube", "name": "fake"}


async def test_fetch_public_profile_returns_none_for_an_unsupported_platform():
    result = await profile_lookup.fetch_public_profile("instagram", _connection("instagram"), "someone")

    assert result is None


async def test_fetch_public_profile_never_raises_on_a_failing_fetcher(monkeypatch):
    async def fake_broken(connection, username):
        raise RuntimeError("boom")

    monkeypatch.setitem(profile_lookup._FETCHER_BY_PLATFORM, "twitter", fake_broken)

    result = await profile_lookup.fetch_public_profile("twitter", _connection("twitter"), "someone")

    assert result is None


# --- fetch_twitter_recent_posts -------------------------------------------


async def test_fetch_twitter_recent_posts_parses_the_real_response_shape(monkeypatch):
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(
                data={
                    "data": [
                        {
                            "text": "Mars mission update",
                            "created_at": "2026-01-01T00:00:00Z",
                            "public_metrics": {"like_count": 100, "retweet_count": 20},
                        },
                        {
                            "text": "New Tesla feature",
                            "created_at": "2026-01-02T00:00:00Z",
                            "public_metrics": {"like_count": 50, "retweet_count": 5},
                        },
                    ]
                }
            )

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_twitter_recent_posts(_connection("twitter"), "@elonmusk")

    assert len(result) == 2
    assert result[0]["text"] == "Mars mission update"
    assert result[0]["likes"] == 100
    assert result[0]["reposts"] == 20

    tool_slug, kwargs = calls[0]
    assert tool_slug == "TWITTER_RECENT_SEARCH"
    assert kwargs["arguments"]["query"] == "from:elonmusk -is:retweet -is:reply"
    # Twitter API enforces a minimum of 10 regardless of what's requested.
    assert kwargs["arguments"]["max_results"] == 10


async def test_fetch_twitter_recent_posts_returns_empty_list_with_no_recent_activity(monkeypatch):
    """Recent Search only covers the last 7 days — an empty result here is
    a genuine, honest possibility, not a failure."""

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={"meta": {"result_count": 0}})

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_twitter_recent_posts(_connection("twitter"), "quiet_account")

    assert result == []


# --- fetch_youtube_recent_videos ------------------------------------------


async def test_fetch_youtube_recent_videos_parses_the_real_response_shape(monkeypatch):
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(
                data={
                    "items": [
                        {
                            "snippet": {
                                "title": "I Gave Away $1,000,000",
                                "description": "Watch until the end.",
                                "publishedAt": "2026-01-01T00:00:00Z",
                            }
                        }
                    ]
                }
            )

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_youtube_recent_videos(_connection("youtube"), "@MrBeast")

    assert len(result) == 1
    assert result[0]["title"] == "I Gave Away $1,000,000"

    tool_slug, kwargs = calls[0]
    assert tool_slug == "YOUTUBE_LIST_CHANNEL_VIDEOS"
    # The handle is passed straight through as channelId — confirmed from
    # the tool's own schema that it accepts a handle directly.
    assert kwargs["arguments"]["channelId"] == "@MrBeast"


async def test_fetch_youtube_recent_videos_returns_empty_list_for_no_uploads(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={"items": []})

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_youtube_recent_videos(_connection("youtube"), "@EmptyChannel")

    assert result == []


# --- fetch_facebook_recent_posts ------------------------------------------


async def test_fetch_facebook_recent_posts_parses_the_real_response_shape(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(
                data={
                    "data": [
                        {
                            "message": "New shoe drop this Friday.",
                            "created_time": "2026-01-01T00:00:00Z",
                            "permalink_url": "https://facebook.com/nike/posts/1",
                        }
                    ]
                }
            )

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_facebook_recent_posts(_connection("facebook"), "nike")

    assert len(result) == 1
    assert result[0]["text"] == "New shoe drop this Friday."
    assert result[0]["url"] == "https://facebook.com/nike/posts/1"


async def test_fetch_facebook_recent_posts_returns_empty_list_without_data(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={})

    monkeypatch.setattr(profile_lookup, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await profile_lookup.fetch_facebook_recent_posts(_connection("facebook"), "not_a_real_page")

    assert result == []


# --- fetch_recent_posts (dispatcher) --------------------------------------


async def test_fetch_recent_posts_dispatches_by_platform(monkeypatch):
    async def fake_youtube(connection, username, *, limit=10):
        return [{"title": "fake"}]

    monkeypatch.setitem(profile_lookup._RECENT_POSTS_FETCHER_BY_PLATFORM, "youtube", fake_youtube)

    result = await profile_lookup.fetch_recent_posts("youtube", _connection("youtube"), "someone")

    assert result == [{"title": "fake"}]


async def test_fetch_recent_posts_returns_empty_list_for_an_unsupported_platform():
    result = await profile_lookup.fetch_recent_posts("instagram", _connection("instagram"), "someone")

    assert result == []


async def test_fetch_recent_posts_never_raises_on_a_failing_fetcher(monkeypatch):
    async def fake_broken(connection, username, *, limit=10):
        raise RuntimeError("boom")

    monkeypatch.setitem(profile_lookup._RECENT_POSTS_FETCHER_BY_PLATFORM, "twitter", fake_broken)

    result = await profile_lookup.fetch_recent_posts("twitter", _connection("twitter"), "someone")

    assert result == []
