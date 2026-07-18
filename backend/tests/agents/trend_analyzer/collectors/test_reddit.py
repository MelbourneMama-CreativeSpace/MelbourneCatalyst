"""Tests for the Reddit collector (PRAW, OAuth read-only mode)."""

from __future__ import annotations

from app.agents.trend_analyzer.collectors import reddit as reddit_module
from app.agents.trend_analyzer.collectors.reddit import RedditCollector


class _FakePost:
    def __init__(self, title, permalink, score, num_comments, selftext=""):
        self.title = title
        self.permalink = permalink
        self.score = score
        self.num_comments = num_comments
        self.selftext = selftext


class _FakeSubreddit:
    def __init__(self, posts):
        self._posts = posts

    def top(self, time_filter="day", limit=10):
        return iter(self._posts)


class _FakeRedditClient:
    def __init__(self, posts_by_subreddit, **kwargs):
        self._posts_by_subreddit = posts_by_subreddit
        self.read_only = False

    def subreddit(self, name):
        if name not in self._posts_by_subreddit:
            raise RuntimeError(f"r/{name} is banned or private")
        return _FakeSubreddit(self._posts_by_subreddit[name])


async def test_collect_skips_when_no_credentials():
    items = await RedditCollector(
        client_id="", client_secret="", subreddits=["marketing"]
    ).collect()
    assert items == []


async def test_collect_parses_posts_into_raw_trend_items(monkeypatch):
    posts = {
        "marketing": [
            _FakePost(
                title="AI marketing trends for 2026",
                permalink="/r/marketing/comments/abc123/ai_marketing_trends/",
                score=342,
                num_comments=51,
            )
        ]
    }
    monkeypatch.setattr(
        reddit_module.praw, "Reddit", lambda **kwargs: _FakeRedditClient(posts)
    )

    items = await RedditCollector(
        client_id="id", client_secret="secret", subreddits=["marketing"]
    ).collect()

    assert len(items) == 1
    item = items[0]
    assert item.title == "AI marketing trends for 2026"
    assert item.url == "https://reddit.com/r/marketing/comments/abc123/ai_marketing_trends/"
    assert item.score == 342.0
    assert item.raw_metadata["subreddit"] == "marketing"


async def test_collect_isolates_a_failing_subreddit(monkeypatch):
    posts = {
        "marketing": [
            _FakePost(
                title="Good post",
                permalink="/r/marketing/comments/1/good/",
                score=10,
                num_comments=1,
            )
        ]
    }
    monkeypatch.setattr(
        reddit_module.praw, "Reddit", lambda **kwargs: _FakeRedditClient(posts)
    )

    items = await RedditCollector(
        client_id="id", client_secret="secret", subreddits=["badsubreddit", "marketing"]
    ).collect()

    assert len(items) == 1
    assert items[0].raw_metadata["subreddit"] == "marketing"
