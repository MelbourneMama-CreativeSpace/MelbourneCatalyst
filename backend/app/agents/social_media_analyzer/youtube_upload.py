"""Real YouTube video upload via Composio — distinct from `publish.py`'s
text-post flow, since YouTube has no text/community-post API at all (see
`publish.py`'s module docstring — checked live against Composio's real
tool catalog, no such action exists there either). Uploading an actual
video file is genuinely possible, though: `YOUTUBE_MULTIPART_UPLOAD_VIDEO`
is real, confirmed against the live catalog.

The upload itself is a two-step dance, confirmed against the installed
`composio-client` SDK's own types (not guessed — its `videoFile` schema
is a `file_uploadable` object requiring an `s3key`, not a raw URL or
bytes):

1. `client.files.create_presigned_url(...)` — tells Composio a file is
   coming (filename/md5/mimetype/which tool+toolkit it's for) and gets
   back a presigned S3 URL to upload to, plus a `key` referencing where
   it'll land.
2. `PUT` the actual bytes to that presigned URL directly — no Composio
   auth needed, the URL itself is the credential, same as any presigned
   S3 upload.
3. `client.tools.execute("YOUTUBE_MULTIPART_UPLOAD_VIDEO", ...)` with
   `videoFile={name, mimetype, s3key: <the key from step 1>}` referencing
   what was just uploaded, plus title/description/category/privacy.

All three steps confirmed against a real upload to a real, connected
YouTube account — not just the SDK's type signatures. The response shape
from step 3 wasn't guessable in advance and turned out to nest the real
video id at `result.data["video"]["id"]`, not the flat top-level `id`
this app's other Composio tool calls happen to use — see
`_extract_video_id`, added after the first real upload's response
crashed the save (a too-narrow assumption, not a failed upload — the
video itself went up fine).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from composio_client import Composio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import PlatformConnection, YouTubeUploadJob
from app.db.session import async_session_factory
from app.security import validate_public_url

logger = logging.getLogger(__name__)

# YouTube's own practical ceiling for a synchronous multipart upload;
# anything larger needs YouTube's resumable upload protocol instead,
# which isn't implemented here.
_UPLOAD_MAX_BYTES = 500_000_000

# A generic, inoffensive default — this app doesn't ask anywhere for a
# YouTube category, and Claude can't safely guess one either. "22" is
# YouTube's own "People & Blogs" category id.
_DEFAULT_CATEGORY_ID = "22"


class YouTubeUploadNotConfiguredError(Exception):
    """Raised when COMPOSIO_API_KEY isn't set."""


class UntrustedVideoUrlError(Exception):
    """Raised when `video_url` isn't one of this app's own Supabase
    Storage public object URLs. This tool exists to publish what a user
    actually attached in this app, not to fetch-and-forward whatever
    content an arbitrary URL happens to point at to their YouTube
    channel — refusing anything else even if it would otherwise pass the
    general SSRF check below."""


def _client() -> Composio:
    return Composio(api_key=settings.COMPOSIO_API_KEY)


def _is_trusted_storage_url(url: str) -> bool:
    if not settings.SUPABASE_URL:
        return False
    parsed = urlparse(url)
    supabase_host = urlparse(settings.SUPABASE_URL).hostname
    return (
        parsed.scheme == "https"
        and bool(supabase_host)
        and parsed.hostname == supabase_host
        and parsed.path.startswith("/storage/v1/object/public/")
    )


async def upload_youtube_video(
    connection: PlatformConnection,
    video_url: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy_status: str = "unlisted",
) -> str:
    """Uploads `video_url`'s content as a real YouTube video on
    `connection`'s connected account. Returns Composio's execution result
    (best-effort stringified — this specific tool's real response shape
    hasn't been seen live in this environment, same caveat as
    `publish.py`'s identity resolvers). Raises `UntrustedVideoUrlError` if
    `video_url` isn't one of this app's own storage URLs; any real
    Composio/network failure propagates as-is."""
    if not settings.COMPOSIO_API_KEY:
        # User-safe message — never name internal env vars here, this can
        # surface directly in chat. Detail goes to the log instead.
        logger.warning("YouTube upload attempted with COMPOSIO_API_KEY unset")
        raise YouTubeUploadNotConfiguredError("YouTube uploads aren't set up yet.")
    if not _is_trusted_storage_url(video_url):
        raise UntrustedVideoUrlError(
            "That video isn't something uploaded through this app — only files "
            "attached in this app's own chat can be published this way."
        )
    await asyncio.to_thread(validate_public_url, video_url)  # defense in depth

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http_client:
        response = await http_client.get(video_url)
        response.raise_for_status()
        content = response.content

    if len(content) > _UPLOAD_MAX_BYTES:
        raise ValueError(
            f"Video is too large ({len(content)} bytes) for this app's upload path "
            f"(caps out at {_UPLOAD_MAX_BYTES} bytes)."
        )

    filename = urlparse(video_url).path.rsplit("/", 1)[-1] or "video.mp4"
    mimetype = response.headers.get("content-type") or "video/mp4"
    md5_hash = hashlib.md5(content).hexdigest()

    client = _client()

    def _request_presigned_url():
        return client.files.create_presigned_url(
            filename=filename,
            md5=md5_hash,
            mimetype=mimetype,
            tool_slug="YOUTUBE_MULTIPART_UPLOAD_VIDEO",
            toolkit_slug="youtube",
        )

    presigned = await asyncio.to_thread(_request_presigned_url)

    async with httpx.AsyncClient(timeout=120.0) as http_client:
        put_response = await http_client.put(
            presigned.new_presigned_url,
            content=content,
            headers={"Content-Type": mimetype},
        )
        put_response.raise_for_status()

    def _execute():
        return client.tools.execute(
            "YOUTUBE_MULTIPART_UPLOAD_VIDEO",
            connected_account_id=connection.composio_connected_account_id,
            # Confirmed live, the hard way: without this, Composio 400s
            # with "User ID is required with connected account" (code
            # 1811, ActionExecute_ConnectedAccountEntityIdRequired) —
            # connected_account_id alone isn't sufficient for tools.execute.
            # Same identifier this app registers the connection under in
            # the first place (see oauth_flow.py's initiate_connection,
            # which passes user_id=str(company_id) to Composio's own
            # /link endpoint) — kept consistent rather than a second,
            # possibly-different identifier.
            user_id=str(connection.company_id),
            arguments={
                "videoFile": {"name": filename, "mimetype": mimetype, "s3key": presigned.key},
                "title": title,
                "description": description,
                "categoryId": _DEFAULT_CATEGORY_ID,
                "privacyStatus": privacy_status,
                "tags": tags or [],
            },
        )

    result = await asyncio.to_thread(_execute)
    return _extract_video_id(result)


# `composio_execution_id` is a String(128) column — sized for a real
# YouTube video id (11 chars), not an entire response dump. Confirmed
# live, the hard way: YOUTUBE_MULTIPART_UPLOAD_VIDEO's real response
# nests the id at `result.data["video"]["id"]`, not a flat top-level
# `.id`/`.data` the way this app's other Composio calls happen to shape
# theirs — the previous generic `getattr(result, "id", None) or
# getattr(result, "data", result)` fallback silently fell through to
# stringifying the *entire* raw response (well over 128 chars) and
# crashed the save with a real StringDataRightTruncationError, after the
# upload itself had already genuinely succeeded. Truncated as a last
# resort so an unexpected future shape degrades to "some execution
# happened, exact id unknown" rather than crashing the whole request
# again.
async def fetch_video_analytics(connection: PlatformConnection, video_ids: list[str]) -> list[dict]:
    """Real view/like/comment counts for up to 50 of `connection`'s own
    already-uploaded YouTube videos, straight from YouTube's Data API via
    Composio's `YOUTUBE_GET_VIDEO_DETAILS_BATCH` — confirmed live against
    the real tool catalog (`client.tools.list(toolkit_slug="youtube")`),
    same verification discipline as everything else in this module. This
    is *not* the separate YouTube Analytics API (watch time, audience
    retention, traffic sources) — no such tool exists in this app's
    Composio YouTube toolkit, only Data-API-level counts (views, likes,
    comments). Returns `result.data["items"]` as-is (each a real `Video`
    resource with `id`/`snippet`/`statistics`, per the tool's own output
    schema — not guessed). Raises on any real Composio/network failure,
    same as every other call in this module."""
    if not settings.COMPOSIO_API_KEY:
        logger.warning("YouTube analytics requested with COMPOSIO_API_KEY unset")
        raise YouTubeUploadNotConfiguredError("YouTube analytics aren't set up yet.")

    client = _client()

    def _execute():
        return client.tools.execute(
            "YOUTUBE_GET_VIDEO_DETAILS_BATCH",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={"id": video_ids, "parts": ["snippet", "statistics"]},
        )

    result = await asyncio.to_thread(_execute)
    data = getattr(result, "data", None)
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def _extract_video_id(result: object) -> str:
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        video = data.get("video")
        if isinstance(video, dict) and video.get("id"):
            return str(video["id"])
    top_level_id = getattr(result, "id", None)
    if top_level_id:
        return str(top_level_id)
    return str(data if data is not None else result)[:128]


async def delete_youtube_video(connection: PlatformConnection, video_id: str) -> None:
    """Permanently deletes a real, previously-uploaded YouTube video —
    confirmed live against Composio's real YouTube toolkit
    (YOUTUBE_DELETE_VIDEO). Composio's own schema requires an explicit
    `confirmDelete: true` as its own safety measure against accidental
    deletion, on top of whatever confirmation this app's own caller
    already required — not redundant, just two independent layers, each
    owned by the party that can actually enforce it. Any real Composio/
    platform-side failure (already deleted, missing permission, expired
    token) propagates as-is."""
    if not settings.COMPOSIO_API_KEY:
        logger.warning("YouTube delete attempted with COMPOSIO_API_KEY unset")
        raise YouTubeUploadNotConfiguredError("YouTube uploads aren't set up yet.")

    client = _client()

    def _execute():
        return client.tools.execute(
            "YOUTUBE_DELETE_VIDEO",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={"videoId": video_id, "confirmDelete": True},
        )

    await asyncio.to_thread(_execute)


def get_video_url(video_id: str) -> str:
    """A real, clickable URL to an uploaded video — unlike
    `publish.get_post_url`'s Facebook/Instagram cases, this needs no
    extra API call at all: YouTube's watch-page URL shape
    (`youtube.com/watch?v={id}`) is stable and well-known, not something
    that needs looking up per video."""
    return f"https://www.youtube.com/watch?v={video_id}"


# ── Retry queue ──────────────────────────────────────────────────────────
# A real upload is three sequential network hops (fetch the video, a
# presigned S3 upload, Composio's own YouTube call) — any one of them can
# fail transiently (a stalled connection, a Composio 5xx) without the
# upload itself being wrong. Queuing means a transient failure retries
# automatically instead of just failing once and leaving the user to
# notice and re-ask.

# Errors where retrying is pointless — the input itself is wrong, not the
# network conditions. Failed immediately rather than burning through
# MAX_YOUTUBE_UPLOAD_ATTEMPTS on something that will never succeed.
_PERMANENT_FAILURES: tuple[type[Exception], ...] = (
    UntrustedVideoUrlError,
    YouTubeUploadNotConfiguredError,
    ValueError,  # oversized video
)


async def _attempt_job(session: AsyncSession, job: YouTubeUploadJob) -> None:
    """One attempt at `job`, mutating it in place and committing. Success
    marks it done; a transient failure leaves it `pending` for the next
    scheduled retry; a permanent failure (see `_PERMANENT_FAILURES`) or
    hitting `MAX_YOUTUBE_UPLOAD_ATTEMPTS` marks it `failed` for good.
    Never raises — same isolate-per-job contract as
    `scheduled_publishing.py`'s `_attempt_publish`."""
    connection = await session.get(PlatformConnection, job.platform_connection_id)
    job.attempt_count += 1
    job.last_attempted_at = datetime.now(timezone.utc)

    if (
        connection is None
        or connection.status != "connected"
        or connection.composio_connected_account_id is None
    ):
        job.status_error = "YouTube is no longer connected for this company."
        if job.attempt_count >= settings.MAX_YOUTUBE_UPLOAD_ATTEMPTS:
            job.status = "failed"
        await session.commit()
        return

    try:
        execution_id = await upload_youtube_video(
            connection,
            job.video_url,
            job.title,
            job.description,
            tags=job.tags,
            privacy_status=job.privacy_status,
        )
    except _PERMANENT_FAILURES as exc:
        logger.warning("YouTube upload job %s failed permanently: %s", job.id, exc)
        job.status = "failed"
        job.status_error = str(exc)[:512]
        await session.commit()
        return
    except Exception as exc:
        logger.exception("YouTube upload job %s failed (attempt %d)", job.id, job.attempt_count)
        job.status_error = str(exc)[:512]
        if job.attempt_count >= settings.MAX_YOUTUBE_UPLOAD_ATTEMPTS:
            job.status = "failed"
        await session.commit()
        return

    job.status = "success"
    job.composio_execution_id = execution_id
    job.status_error = None
    try:
        await session.commit()
    except Exception:
        # The real upload already happened — execution_id proves it, this
        # isn't a failed upload. If saving that fact fails too (confirmed
        # live: a too-long execution_id crashed exactly this commit once),
        # the only safe move is to freeze the job rather than leave it
        # `pending`: `run_scheduled_youtube_uploads` retries anything
        # `pending`, and retrying here means re-uploading the same video a
        # second time to the user's real channel. Freezing loses the
        # composio_execution_id from the row, so it's preserved in the
        # error text instead for manual reconciliation.
        logger.exception(
            "YouTube upload job %s: upload succeeded (execution id=%s) but saving "
            "the result failed — freezing rather than leaving it retryable",
            job.id,
            execution_id,
        )
        await session.rollback()
        job.status = "failed"
        job.status_error = (
            f"Uploaded successfully (execution id: {execution_id}) but the app "
            "failed to save this — do not retry; needs manual reconciliation."
        )[:512]
        await session.commit()


async def enqueue_youtube_upload(
    session: AsyncSession,
    connection: PlatformConnection,
    video_url: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy_status: str = "unlisted",
) -> YouTubeUploadJob:
    """Creates a queued upload job and makes one immediate attempt — the
    common case (a working connection, a real video) succeeds right away
    and the caller can say so directly; a transient failure leaves the
    job `pending` for `run_scheduled_youtube_uploads` to keep retrying
    without the caller having to do anything else. `privacy_status` is a
    real, per-upload choice (unlisted/public/private) — defaults to the
    safest option, not hardcoded to it."""
    job = YouTubeUploadJob(
        id=uuid.uuid4(),
        platform_connection_id=connection.id,
        video_url=video_url,
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy_status,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    await _attempt_job(session, job)
    return job


async def run_scheduled_youtube_uploads() -> None:
    """Retries every YouTube upload job still `pending` — failures
    isolated per job, same pattern as every other scheduled batch job in
    this codebase."""
    async with async_session_factory() as session:
        pending_ids = (
            (
                await session.execute(
                    select(YouTubeUploadJob.id).where(YouTubeUploadJob.status == "pending")
                )
            )
            .scalars()
            .all()
        )

    for job_id in pending_ids:
        try:
            async with async_session_factory() as session:
                job = await session.get(YouTubeUploadJob, job_id)
                if job is None or job.status != "pending":
                    continue  # succeeded/failed/vanished since the batch was listed
                await _attempt_job(session, job)
        except Exception:
            logger.exception("Unexpected error retrying YouTube upload job %s", job_id)
