"""Tests for Composio-backed post publishing."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.agents.social_media_analyzer import publish


def _configure(monkeypatch, **overrides):
    monkeypatch.setattr(publish.settings, "COMPOSIO_API_KEY", "test-composio-key")
    monkeypatch.setattr(publish.settings, "COMPOSIO_LINKEDIN_AUTH_CONFIG_ID", "ac_linkedin_123")
    monkeypatch.setattr(
        publish.settings, "COMPOSIO_LINKEDIN_POST_TOOL_SLUG", "LINKEDIN_CREATE_LINKED_IN_POST"
    )
    monkeypatch.setattr(publish.settings, "COMPOSIO_FACEBOOK_AUTH_CONFIG_ID", "ac_facebook_123")
    monkeypatch.setattr(publish.settings, "COMPOSIO_FACEBOOK_POST_TOOL_SLUG", "FACEBOOK_CREATE_POST")
    monkeypatch.setattr(publish.settings, "COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID", "ac_instagram_123")
    for setting_name, value in overrides.items():
        monkeypatch.setattr(publish.settings, setting_name, value)


def _connection(platform: str, **overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        platform=platform,
        composio_connected_account_id="conn-123",
        external_account_id=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeSession:
    """No-op stand-in — `publish_post` only ever calls `.add()` on it
    (to stage the resolved identity for the caller's own later commit),
    never `.commit()` itself."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


async def test_publish_post_raises_when_api_key_not_set(monkeypatch):
    _configure(monkeypatch, COMPOSIO_API_KEY="")

    with pytest.raises(publish.PublishNotConfiguredError):
        await publish.publish_post(_FakeSession(), _connection("linkedin"), "hello world")


async def test_publish_post_raises_when_post_tool_slug_not_set(monkeypatch):
    # This is the real, current state for youtube/instagram in this
    # environment — no post action exists for either (see publish.py's
    # module docstring), not just an unconfirmed slug.
    _configure(monkeypatch, COMPOSIO_LINKEDIN_POST_TOOL_SLUG="")

    with pytest.raises(publish.PublishNotConfiguredError):
        await publish.publish_post(_FakeSession(), _connection("linkedin"), "hello world")


async def test_publish_post_raises_for_unknown_platform(monkeypatch):
    _configure(monkeypatch)

    with pytest.raises(ValueError, match="Unknown platform"):
        await publish.publish_post(_FakeSession(), _connection("myspace"), "hello world")


async def test_publish_post_resolves_and_caches_linkedin_author_urn(monkeypatch):
    _configure(monkeypatch)

    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            if tool_slug == "LINKEDIN_GET_MY_INFO":
                return SimpleNamespace(data={"sub": "urn:li:person:abc123"})
            return SimpleNamespace(id="exec-abc123")

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    session = _FakeSession()
    connection = _connection("linkedin")
    result = await publish.publish_post(session, connection, "A real ready-to-publish caption.")

    assert result == "exec-abc123"
    # Resolved once, then cached on the connection row for next time.
    assert connection.external_account_id == "urn:li:person:abc123"
    assert connection in session.added

    identity_call, post_call = calls
    assert identity_call[0] == "LINKEDIN_GET_MY_INFO"
    # Regression: this identity-resolver call is a *separate*
    # tools.execute() from the main post call below and got missed the
    # first time `user_id` was added — surfaced as a real 400 ("User ID is
    # required with connected account", code 1811) on an actual LinkedIn
    # publish whose identity hadn't been resolved/cached yet.
    assert identity_call[1]["user_id"] == str(connection.company_id)
    assert post_call[0] == "LINKEDIN_CREATE_LINKED_IN_POST"
    assert post_call[1]["connected_account_id"] == "conn-123"
    assert post_call[1]["user_id"] == str(connection.company_id)
    assert post_call[1]["arguments"] == {
        "commentary": "A real ready-to-publish caption.",
        "author": "urn:li:person:abc123",
    }


async def test_publish_post_skips_identity_lookup_when_already_cached(monkeypatch):
    _configure(monkeypatch)

    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append(tool_slug)
            return SimpleNamespace(id="exec-abc123")

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    connection = _connection("linkedin", external_account_id="urn:li:person:already-known")
    await publish.publish_post(_FakeSession(), connection, "text")

    # Only the post call — no LINKEDIN_GET_MY_INFO lookup needed.
    assert calls == ["LINKEDIN_CREATE_LINKED_IN_POST"]


async def test_publish_post_uses_facebook_page_id_and_message(monkeypatch):
    _configure(monkeypatch)

    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            if tool_slug == "FACEBOOK_LIST_MANAGED_PAGES":
                return SimpleNamespace(data={"data": [{"id": "page-999", "name": "My Page"}]})
            return SimpleNamespace(id="exec-fb-1", kwargs=kwargs)

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    session = _FakeSession()
    connection = _connection("facebook")
    result = await publish.publish_post(session, connection, "Hello page followers.")

    assert result == "exec-fb-1"
    assert connection.external_account_id == "page-999"

    identity_call, post_call = calls
    assert identity_call[0] == "FACEBOOK_LIST_MANAGED_PAGES"
    # Same regression as LinkedIn's identity call — a separate
    # tools.execute() that needs its own user_id.
    assert identity_call[1]["user_id"] == str(connection.company_id)
    assert post_call[1]["user_id"] == str(connection.company_id)


async def test_publish_post_uses_facebook_photo_post_when_media_url_is_set(monkeypatch):
    """Regression test for a real bug: FACEBOOK_CREATE_POST (the plain
    text tool) has no image parameter at all — a post with `media_url`
    set went out as *text only*, silently dropping the attached photo.
    Confirmed live: a real post existed on the real Facebook page with
    the right caption but no image. A real photo needs the different
    FACEBOOK_CREATE_PHOTO_POST tool."""
    _configure(monkeypatch)

    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            if tool_slug == "FACEBOOK_LIST_MANAGED_PAGES":
                return SimpleNamespace(data={"data": [{"id": "page-999", "name": "My Page"}]})
            return SimpleNamespace(data={"id": "photo-1", "post_id": "page-999_post-1"})

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    session = _FakeSession()
    connection = _connection("facebook")
    result = await publish.publish_post(
        session, connection, "Just this.", media_url="https://storage/img.jpg"
    )

    assert result == "page-999_post-1"

    identity_call, photo_call = calls
    assert identity_call[0] == "FACEBOOK_LIST_MANAGED_PAGES"
    assert photo_call[0] == "FACEBOOK_CREATE_PHOTO_POST"
    assert photo_call[1]["user_id"] == str(connection.company_id)
    assert photo_call[1]["arguments"] == {
        "url": "https://storage/img.jpg",
        "message": "Just this.",
        "page_id": "page-999",
        "published": True,
    }


async def test_publish_post_uses_plain_text_post_when_no_media_url(monkeypatch):
    """A Facebook post genuinely can be text-only — media_url is optional,
    not required the way it is for Instagram. Confirms the photo-post
    branch above doesn't accidentally become the only path."""
    _configure(monkeypatch)

    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append(tool_slug)
            if tool_slug == "FACEBOOK_LIST_MANAGED_PAGES":
                return SimpleNamespace(data={"data": [{"id": "page-999"}]})
            return SimpleNamespace(data={"id": "exec-fb-text"})

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await publish.publish_post(_FakeSession(), _connection("facebook"), "Text only.")

    assert result == "exec-fb-text"
    assert "FACEBOOK_CREATE_PHOTO_POST" not in calls
    assert "FACEBOOK_CREATE_POST" in calls


def test_extract_response_id_prefers_post_id_over_bare_id():
    """Regression test for a real bug: the previous extraction
    (`getattr(response, "id", None) or getattr(response, "data",
    response)`) checked a top-level `.id` that never actually exists on
    Composio's response wrapper, then fell through to stringifying the
    *entire* `.data` dict — producing a stored id like `"{'id':
    '2109922212367336_1460783426082148'}"` for a real post that had
    genuinely succeeded, confirmed live via Facebook's own Graph API."""
    response = SimpleNamespace(data={"id": "photo-1", "post_id": "page_post"})
    assert publish._extract_response_id(response) == "page_post"


def test_extract_response_id_uses_linkedin_x_restli_id():
    """LinkedIn's real, required response field is `x_restli_id`, not
    `id` — confirmed against the real tool's output schema, not assumed."""
    response = SimpleNamespace(data={"id": None, "x_restli_id": "urn:li:share:123"})
    assert publish._extract_response_id(response) == "urn:li:share:123"


def test_extract_response_id_falls_back_to_bare_id():
    response = SimpleNamespace(data={"id": "exec-abc123"})
    assert publish._extract_response_id(response) == "exec-abc123"


async def test_publish_post_raises_when_facebook_identity_cannot_be_resolved(monkeypatch):
    _configure(monkeypatch)

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={"data": []})  # no managed pages

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    with pytest.raises(publish.PublishIdentityUnresolvedError):
        await publish.publish_post(_FakeSession(), _connection("facebook"), "text")


async def test_publish_post_requires_media_url_for_instagram(monkeypatch):
    """Instagram has no text-only post at all — confirmed live against the
    real Composio Instagram toolkit (only INSTAGRAM_CREATE_MEDIA_CONTAINER
    + INSTAGRAM_CREATE_POST exist). Must fail fast with a clear reason
    rather than attempting a call that Meta's API would reject anyway."""
    _configure(monkeypatch)

    with pytest.raises(publish.InstagramMediaRequiredError):
        await publish.publish_post(_FakeSession(), _connection("instagram"), "A caption.")


async def test_publish_post_raises_when_instagram_not_configured(monkeypatch):
    _configure(monkeypatch, COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID="")

    with pytest.raises(publish.PublishNotConfiguredError):
        await publish.publish_post(
            _FakeSession(), _connection("instagram"), "A caption.", media_url="https://x/img.jpg"
        )


async def test_publish_post_performs_the_instagram_two_step_flow(monkeypatch):
    _configure(monkeypatch)

    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            if tool_slug == "INSTAGRAM_GET_USER_INFO":
                return SimpleNamespace(data={"id": "17841400000000000"})
            if tool_slug == "INSTAGRAM_CREATE_MEDIA_CONTAINER":
                return SimpleNamespace(data={"id": "container-abc"})
            if tool_slug == "INSTAGRAM_CREATE_POST":
                return SimpleNamespace(data={"id": "media-xyz"})
            raise AssertionError(f"unexpected tool: {tool_slug}")

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    session = _FakeSession()
    connection = _connection("instagram")
    result = await publish.publish_post(
        session, connection, "A whimsical caption.", media_url="https://storage/img.jpg"
    )

    assert result == "media-xyz"
    assert connection.external_account_id == "17841400000000000"

    identity_call, container_call, post_call = calls
    assert identity_call[0] == "INSTAGRAM_GET_USER_INFO"
    assert identity_call[1]["user_id"] == str(connection.company_id)

    assert container_call[0] == "INSTAGRAM_CREATE_MEDIA_CONTAINER"
    assert container_call[1]["user_id"] == str(connection.company_id)
    assert container_call[1]["arguments"] == {
        "ig_user_id": "17841400000000000",
        "image_url": "https://storage/img.jpg",
        "caption": "A whimsical caption.",
    }

    assert post_call[0] == "INSTAGRAM_CREATE_POST"
    assert post_call[1]["user_id"] == str(connection.company_id)
    assert post_call[1]["arguments"] == {
        "ig_user_id": "17841400000000000",
        "creation_id": "container-abc",
    }


async def test_publish_post_propagates_a_real_composio_failure(monkeypatch):
    _configure(monkeypatch)

    class _FailingTools:
        def execute(self, tool_slug, **kwargs):
            raise RuntimeError("Composio: connected account is expired")

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FailingTools()))

    with pytest.raises(RuntimeError, match="expired"):
        await publish.publish_post(
            _FakeSession(), _connection("linkedin", external_account_id="urn:li:person:x"), "text"
        )


async def test_delete_post_uses_the_real_linkedin_delete_tool_and_arg_name(monkeypatch):
    """Confirmed live against Composio's real LinkedIn toolkit:
    LINKEDIN_DELETE_POST (the modern Posts API endpoint, not the legacy
    LINKEDIN_DELETE_UGC_POST or the older LINKEDIN_DELETE_LINKED_IN_POST),
    argument name post_urn — matches what publish_post's own
    x_restli_id-based extraction already stores
    (e.g. "urn:li:share:7493009415151738880")."""
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(data={})

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    connection = _connection("linkedin")
    await publish.delete_post(connection, "urn:li:share:7493009415151738880")

    tool_slug, kwargs = calls[0]
    assert tool_slug == "LINKEDIN_DELETE_POST"
    assert kwargs["connected_account_id"] == "conn-123"
    assert kwargs["user_id"] == str(connection.company_id)
    assert kwargs["arguments"] == {"post_urn": "urn:li:share:7493009415151738880"}


async def test_delete_post_uses_the_real_facebook_delete_tool_and_arg_name(monkeypatch):
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(data={})

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    connection = _connection("facebook")
    await publish.delete_post(connection, "2109922212367336_1460783426082148")

    tool_slug, kwargs = calls[0]
    assert tool_slug == "FACEBOOK_DELETE_POST"
    assert kwargs["arguments"] == {"post_id": "2109922212367336_1460783426082148"}


async def test_delete_post_raises_for_instagram():
    """Instagram genuinely has no delete-media action anywhere in
    Composio's real Instagram toolkit — confirmed live, not assumed."""
    with pytest.raises(publish.DeleteNotSupportedError):
        await publish.delete_post(_connection("instagram"), "some-id")


async def test_get_post_url_constructs_the_real_linkedin_permalink_format():
    """LinkedIn has no permalink field in any of its own API responses —
    confirmed against LINKEDIN_GET_POST_CONTENT's real output schema.
    https://www.linkedin.com/feed/update/{urn}/ is LinkedIn's own
    long-standing documented convention for a share URN, not guessed."""
    connection = _connection("linkedin")
    url = await publish.get_post_url(connection, "urn:li:share:7493009415151738880")
    assert url == "https://www.linkedin.com/feed/update/urn:li:share:7493009415151738880/"


async def test_get_post_url_fetches_the_real_facebook_permalink(monkeypatch):
    """Deliberately NOT constructed by hand — confirmed live that
    Facebook's real permalink_url does not simply combine as
    facebook.com/{post_id}."""

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            assert tool_slug == "FACEBOOK_GET_POST"
            assert kwargs["arguments"] == {"post_id": "2109922212367336_1460783426082148"}
            return SimpleNamespace(
                data={"permalink_url": "https://www.facebook.com/1460802549413569/posts/1460783426082148"}
            )

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    connection = _connection("facebook")
    url = await publish.get_post_url(connection, "2109922212367336_1460783426082148")

    assert url == "https://www.facebook.com/1460802549413569/posts/1460783426082148"


async def test_get_post_url_fetches_the_real_instagram_permalink(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            assert tool_slug == "INSTAGRAM_GET_IG_MEDIA"
            assert kwargs["arguments"] == {"ig_media_id": "media-123"}
            return SimpleNamespace(data={"permalink": "https://www.instagram.com/p/AbC123/"})

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    connection = _connection("instagram")
    url = await publish.get_post_url(connection, "media-123")

    assert url == "https://www.instagram.com/p/AbC123/"


async def test_get_post_url_is_best_effort_and_never_raises(monkeypatch):
    """A failed lookup must not turn a genuinely successful publish into
    an error — the caller just gets no link."""

    class _FailingTools:
        def execute(self, tool_slug, **kwargs):
            raise RuntimeError("Composio: rate limited")

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FailingTools()))

    url = await publish.get_post_url(_connection("facebook"), "some-id")

    assert url is None
