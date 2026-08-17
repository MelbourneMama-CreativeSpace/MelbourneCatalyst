"""Tests for real YouTube video upload via Composio."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
import respx
from sqlalchemy import select

from app.agents.social_media_analyzer import youtube_upload
from app.db.models import Company, PlatformConnection, YouTubeUploadJob


def _connection(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        platform="youtube",
        composio_connected_account_id="conn-yt-123",
        status="connected",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _configure(monkeypatch, **overrides):
    monkeypatch.setattr(youtube_upload.settings, "COMPOSIO_API_KEY", "test-composio-key")
    monkeypatch.setattr(youtube_upload.settings, "SUPABASE_URL", "https://test-project.supabase.co")
    # The general SSRF guard does real DNS resolution — irrelevant to what
    # this module's own tests are about, same convention as
    # test_scraper.py for the same reason.
    monkeypatch.setattr(youtube_upload, "validate_public_url", lambda url: None)
    for setting_name, value in overrides.items():
        monkeypatch.setattr(youtube_upload.settings, setting_name, value)


_TRUSTED_URL = "https://test-project.supabase.co/storage/v1/object/public/media-library/some/video.mp4"


async def test_upload_raises_when_api_key_not_set(monkeypatch):
    _configure(monkeypatch, COMPOSIO_API_KEY="")

    with pytest.raises(youtube_upload.YouTubeUploadNotConfiguredError):
        await youtube_upload.upload_youtube_video(_connection(), _TRUSTED_URL, "T", "D")


async def test_upload_rejects_a_url_not_from_this_apps_own_storage(monkeypatch):
    _configure(monkeypatch)

    with pytest.raises(youtube_upload.UntrustedVideoUrlError):
        await youtube_upload.upload_youtube_video(
            _connection(), "https://evil.example.com/video.mp4", "T", "D"
        )


async def test_upload_rejects_a_supabase_url_for_a_different_project(monkeypatch):
    _configure(monkeypatch)

    with pytest.raises(youtube_upload.UntrustedVideoUrlError):
        await youtube_upload.upload_youtube_video(
            _connection(),
            "https://someone-elses-project.supabase.co/storage/v1/object/public/media-library/x.mp4",
            "T",
            "D",
        )


async def test_upload_rejects_a_trusted_host_with_an_untrusted_path(monkeypatch):
    _configure(monkeypatch)

    with pytest.raises(youtube_upload.UntrustedVideoUrlError):
        await youtube_upload.upload_youtube_video(
            _connection(),
            "https://test-project.supabase.co/rest/v1/some-other-endpoint",
            "T",
            "D",
        )


@respx.mock
async def test_upload_performs_the_full_presign_put_execute_flow(monkeypatch):
    _configure(monkeypatch)
    respx.get(_TRUSTED_URL).mock(
        return_value=httpx.Response(
            200, content=b"fake video bytes", headers={"content-type": "video/mp4"}
        )
    )
    respx.put("https://storage.composio.dev/upload-here").mock(return_value=httpx.Response(200))

    captured: dict = {}

    class _FakeFiles:
        def create_presigned_url(self, **kwargs):
            captured["presign_kwargs"] = kwargs
            return SimpleNamespace(
                key="projects/pr_x/requests/youtube/video.mp4",
                new_presigned_url="https://storage.composio.dev/upload-here",
            )

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            captured["tool_slug"] = tool_slug
            captured["execute_kwargs"] = kwargs
            # Real confirmed shape (a live upload, not guessed) — the
            # video id is nested under data["video"]["id"], not a flat
            # top-level `id`.
            return SimpleNamespace(data={"video": {"id": "yt-video-abc123"}})

    monkeypatch.setattr(
        youtube_upload, "_client", lambda: SimpleNamespace(files=_FakeFiles(), tools=_FakeTools())
    )

    connection = _connection()
    result = await youtube_upload.upload_youtube_video(
        connection, _TRUSTED_URL, "My Video", "A description", tags=["yc", "startup"]
    )

    assert result == "yt-video-abc123"
    assert captured["presign_kwargs"]["tool_slug"] == "YOUTUBE_MULTIPART_UPLOAD_VIDEO"
    assert captured["presign_kwargs"]["toolkit_slug"] == "youtube"
    assert captured["presign_kwargs"]["mimetype"] == "video/mp4"
    assert captured["tool_slug"] == "YOUTUBE_MULTIPART_UPLOAD_VIDEO"
    assert captured["execute_kwargs"]["user_id"] == str(connection.company_id)

    args = captured["execute_kwargs"]["arguments"]
    assert args["videoFile"] == {
        "name": "video.mp4",
        "mimetype": "video/mp4",
        "s3key": "projects/pr_x/requests/youtube/video.mp4",
    }
    assert args["title"] == "My Video"
    assert args["description"] == "A description"
    assert args["privacyStatus"] == "unlisted"
    assert args["categoryId"] == "22"
    assert args["tags"] == ["yc", "startup"]
    assert captured["execute_kwargs"]["connected_account_id"] == "conn-yt-123"


def test_extract_video_id_from_the_real_confirmed_response_shape():
    # A real live upload's actual response — the video id is nested, not
    # a flat top-level `id` (that assumption crashed the very first real
    # upload's save with StringDataRightTruncationError, since the whole
    # raw response got stringified into a 128-char column instead).
    result = SimpleNamespace(
        data={
            "video": {
                "id": "6OnF6SGB8k8",
                "kind": "youtube#video",
                "status": {"privacyStatus": "unlisted", "uploadStatus": "uploaded"},
            }
        }
    )
    assert youtube_upload._extract_video_id(result) == "6OnF6SGB8k8"


def test_extract_video_id_falls_back_to_a_flat_top_level_id():
    result = SimpleNamespace(id="some-other-execution-id", data=None)
    assert youtube_upload._extract_video_id(result) == "some-other-execution-id"


def test_extract_video_id_truncates_an_unrecognized_shape_instead_of_crashing():
    # No "video" key, no top-level id — some future/unexpected response
    # shape. Must degrade to a short, storable string, not the full dump
    # that broke the very first real upload's save.
    result = SimpleNamespace(data={"unexpected": "x" * 500}, id=None)
    extracted = youtube_upload._extract_video_id(result)
    assert len(extracted) <= 128


async def test_delete_youtube_video_uses_the_real_tool_and_confirm_flag(monkeypatch):
    """Confirmed live against Composio's real YouTube toolkit
    (YOUTUBE_DELETE_VIDEO) — its own schema requires an explicit
    confirmDelete: true as Composio's own safety measure, independent of
    whatever confirmation this app's own caller already required."""
    _configure(monkeypatch)

    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(data={})

    monkeypatch.setattr(youtube_upload, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    connection = _connection()
    await youtube_upload.delete_youtube_video(connection, "6OnF6SGB8k8")

    tool_slug, kwargs = calls[0]
    assert tool_slug == "YOUTUBE_DELETE_VIDEO"
    assert kwargs["connected_account_id"] == "conn-yt-123"
    assert kwargs["user_id"] == str(connection.company_id)
    assert kwargs["arguments"] == {"videoId": "6OnF6SGB8k8", "confirmDelete": True}


def test_get_video_url_constructs_the_real_watch_url():
    assert youtube_upload.get_video_url("6OnF6SGB8k8") == "https://www.youtube.com/watch?v=6OnF6SGB8k8"


async def test_delete_youtube_video_raises_when_not_configured(monkeypatch):
    _configure(monkeypatch, COMPOSIO_API_KEY="")

    with pytest.raises(youtube_upload.YouTubeUploadNotConfiguredError):
        await youtube_upload.delete_youtube_video(_connection(), "6OnF6SGB8k8")


@respx.mock
async def test_upload_rejects_oversized_video(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(youtube_upload, "_UPLOAD_MAX_BYTES", 10)
    respx.get(_TRUSTED_URL).mock(
        return_value=httpx.Response(
            200,
            content=b"this is definitely more than ten bytes",
            headers={"content-type": "video/mp4"},
        )
    )

    with pytest.raises(ValueError, match="too large"):
        await youtube_upload.upload_youtube_video(_connection(), _TRUSTED_URL, "T", "D")


@respx.mock
async def test_upload_propagates_a_real_composio_failure(monkeypatch):
    _configure(monkeypatch)
    respx.get(_TRUSTED_URL).mock(
        return_value=httpx.Response(200, content=b"bytes", headers={"content-type": "video/mp4"})
    )

    class _FailingFiles:
        def create_presigned_url(self, **kwargs):
            raise RuntimeError("Composio: quota exceeded")

    monkeypatch.setattr(youtube_upload, "_client", lambda: SimpleNamespace(files=_FailingFiles()))

    with pytest.raises(RuntimeError, match="quota exceeded"):
        await youtube_upload.upload_youtube_video(_connection(), _TRUSTED_URL, "T", "D")


# ── Retry queue ──────────────────────────────────────────────────────────


async def _seed_youtube_connection(test_session_factory, **overrides) -> PlatformConnection:
    company_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url=f"https://example.com/{company_id}", status="complete"))
        defaults = dict(
            id=connection_id,
            company_id=company_id,
            platform="youtube",
            status="connected",
            composio_connected_account_id="conn-yt-123",
        )
        defaults.update(overrides)
        session.add(PlatformConnection(**defaults))
        await session.commit()
    async with test_session_factory() as session:
        return await session.get(PlatformConnection, connection_id)


@respx.mock
async def test_enqueue_youtube_upload_succeeds_on_first_attempt(test_session_factory, monkeypatch):
    _configure(monkeypatch)
    connection = await _seed_youtube_connection(test_session_factory)
    respx.get(_TRUSTED_URL).mock(
        return_value=httpx.Response(200, content=b"bytes", headers={"content-type": "video/mp4"})
    )
    respx.put("https://storage.composio.dev/upload-here").mock(return_value=httpx.Response(200))

    class _FakeFiles:
        def create_presigned_url(self, **kwargs):
            return SimpleNamespace(
                key="k", new_presigned_url="https://storage.composio.dev/upload-here"
            )

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            # Real confirmed shape (a live upload, not guessed) — the
            # video id is nested under data["video"]["id"], not a flat
            # top-level `id`.
            return SimpleNamespace(data={"video": {"id": "yt-video-abc123"}})

    monkeypatch.setattr(
        youtube_upload, "_client", lambda: SimpleNamespace(files=_FakeFiles(), tools=_FakeTools())
    )

    async with test_session_factory() as session:
        job = await youtube_upload.enqueue_youtube_upload(
            session, connection, _TRUSTED_URL, "My Video", "D"
        )

    assert job.status == "success"
    assert job.composio_execution_id == "yt-video-abc123"
    assert job.attempt_count == 1

    # And it's really persisted, not just the in-memory object mutated.
    async with test_session_factory() as session:
        stored = await session.get(YouTubeUploadJob, job.id)
        assert stored.status == "success"


@respx.mock
async def test_enqueue_youtube_upload_passes_through_an_explicit_privacy_status(
    test_session_factory, monkeypatch
):
    """privacy_status used to be hardcoded to 'unlisted' at every layer
    above upload_youtube_video() itself, even though that function always
    accepted a real parameter — confirmed end to end here, not just at the
    function-signature level."""
    _configure(monkeypatch)
    connection = await _seed_youtube_connection(test_session_factory)
    respx.get(_TRUSTED_URL).mock(
        return_value=httpx.Response(200, content=b"bytes", headers={"content-type": "video/mp4"})
    )
    respx.put("https://storage.composio.dev/upload-here").mock(return_value=httpx.Response(200))

    captured: dict = {}

    class _FakeFiles:
        def create_presigned_url(self, **kwargs):
            return SimpleNamespace(
                key="k", new_presigned_url="https://storage.composio.dev/upload-here"
            )

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            captured["arguments"] = kwargs["arguments"]
            return SimpleNamespace(data={"video": {"id": "yt-video-abc123"}})

    monkeypatch.setattr(
        youtube_upload, "_client", lambda: SimpleNamespace(files=_FakeFiles(), tools=_FakeTools())
    )

    async with test_session_factory() as session:
        job = await youtube_upload.enqueue_youtube_upload(
            session, connection, _TRUSTED_URL, "My Video", "D", privacy_status="public"
        )

    assert job.status == "success"
    assert job.privacy_status == "public"
    assert captured["arguments"]["privacyStatus"] == "public"

    async with test_session_factory() as session:
        stored = await session.get(YouTubeUploadJob, job.id)
        assert stored.privacy_status == "public"


@respx.mock
async def test_enqueue_youtube_upload_stays_pending_on_a_transient_failure(
    test_session_factory, monkeypatch
):
    _configure(monkeypatch)
    connection = await _seed_youtube_connection(test_session_factory)
    respx.get(_TRUSTED_URL).mock(
        return_value=httpx.Response(200, content=b"bytes", headers={"content-type": "video/mp4"})
    )

    class _FailingFiles:
        def create_presigned_url(self, **kwargs):
            raise RuntimeError("Composio: 503 upstream error")

    monkeypatch.setattr(youtube_upload, "_client", lambda: SimpleNamespace(files=_FailingFiles()))

    async with test_session_factory() as session:
        job = await youtube_upload.enqueue_youtube_upload(
            session, connection, _TRUSTED_URL, "My Video", "D"
        )

    assert job.status == "pending"  # will be retried, not given up on
    assert job.attempt_count == 1
    assert "503" in job.status_error


async def test_enqueue_youtube_upload_fails_immediately_on_an_untrusted_url(
    test_session_factory, monkeypatch
):
    _configure(monkeypatch)
    connection = await _seed_youtube_connection(test_session_factory)

    async with test_session_factory() as session:
        job = await youtube_upload.enqueue_youtube_upload(
            session, connection, "https://evil.example.com/video.mp4", "T", "D"
        )

    # A bad URL is never going to succeed no matter how many times it's
    # retried — failed on the first attempt, not left pending.
    assert job.status == "failed"
    assert job.attempt_count == 1


async def test_attempt_job_gives_up_after_max_attempts(test_session_factory, monkeypatch):
    _configure(monkeypatch)
    connection = await _seed_youtube_connection(test_session_factory)
    monkeypatch.setattr(youtube_upload.settings, "MAX_YOUTUBE_UPLOAD_ATTEMPTS", 2)

    async with test_session_factory() as session:
        job = YouTubeUploadJob(
            id=uuid.uuid4(),
            platform_connection_id=connection.id,
            video_url=_TRUSTED_URL,
            title="T",
            description="D",
            attempt_count=1,  # already tried once
        )
        session.add(job)
        await session.commit()

    async def _always_fails(*args, **kwargs):
        raise RuntimeError("still broken")

    monkeypatch.setattr(youtube_upload, "upload_youtube_video", _always_fails)

    async with test_session_factory() as session:
        stored = await session.get(YouTubeUploadJob, job.id)
        await youtube_upload._attempt_job(session, stored)

    assert stored.attempt_count == 2
    assert stored.status == "failed"  # hit MAX_YOUTUBE_UPLOAD_ATTEMPTS


async def test_run_scheduled_youtube_uploads_isolates_per_job_failures(
    test_session_factory, monkeypatch
):
    _configure(monkeypatch)
    monkeypatch.setattr(youtube_upload, "async_session_factory", test_session_factory)
    connection = await _seed_youtube_connection(test_session_factory)

    async with test_session_factory() as session:
        ok_job = YouTubeUploadJob(
            id=uuid.uuid4(),
            platform_connection_id=connection.id,
            video_url=_TRUSTED_URL,
            title="Good one",
            description="D",
        )
        broken_job = YouTubeUploadJob(
            id=uuid.uuid4(),
            platform_connection_id=connection.id,
            video_url="https://evil.example.com/video.mp4",  # untrusted -> fails permanently
            title="Bad one",
            description="D",
        )
        session.add_all([ok_job, broken_job])
        await session.commit()

    async def _fake_upload(connection, video_url, title, description, tags=None, privacy_status="unlisted"):
        if video_url == _TRUSTED_URL:
            return "yt-video-ok"
        raise youtube_upload.UntrustedVideoUrlError("not one of this app's own storage URLs")

    monkeypatch.setattr(youtube_upload, "upload_youtube_video", _fake_upload)

    await youtube_upload.run_scheduled_youtube_uploads()

    async with test_session_factory() as session:
        ok_result = await session.get(YouTubeUploadJob, ok_job.id)
        broken_result = await session.get(YouTubeUploadJob, broken_job.id)

    assert ok_result.status == "success"
    assert broken_result.status == "failed"


async def test_run_scheduled_youtube_uploads_skips_success_and_failed_jobs(
    test_session_factory, monkeypatch
):
    _configure(monkeypatch)
    monkeypatch.setattr(youtube_upload, "async_session_factory", test_session_factory)
    connection = await _seed_youtube_connection(test_session_factory)

    async with test_session_factory() as session:
        already_done = YouTubeUploadJob(
            id=uuid.uuid4(),
            platform_connection_id=connection.id,
            video_url=_TRUSTED_URL,
            title="Already uploaded",
            description="D",
            status="success",
            composio_execution_id="yt-old",
        )
        session.add(already_done)
        await session.commit()

    called = False

    async def _fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("should not retry an already-succeeded job")

    monkeypatch.setattr(youtube_upload, "upload_youtube_video", _fail_if_called)

    await youtube_upload.run_scheduled_youtube_uploads()

    assert called is False
