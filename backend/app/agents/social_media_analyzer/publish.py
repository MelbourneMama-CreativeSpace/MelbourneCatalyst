"""Publishing a post via Composio's tool-execution endpoint.

Same shape as `oauth_flow.py` — synchronous `composio-client` calls run
via `asyncio.to_thread`, `_client()` constructs the client fresh per call.
Uses `client.tools.execute()` (confirmed against the real installed
`composio-client` 1.42.0 package, `resources/tools.py`), the same
low-level action-execution endpoint Composio's own agentic-tool-use
integrations use — not guessed, verified by reading the installed SDK.

Every platform's "create a post" tool takes a *different* argument shape
— confirmed live against Composio's real tool catalog, not assumed:
Facebook's `FACEBOOK_CREATE_POST` needs `{page_id, message}`, LinkedIn's
`LINKEDIN_CREATE_LINKED_IN_POST` needs `{author: <URN>, commentary}`. A
single hardcoded `{"text": ...}` (this module's previous shape) only ever
worked by coincidence for a tool that happened to name its field `text`.

The `page_id`/`author` identifiers aren't something Composio's OAuth
connection hands over directly — they're resolved separately (which page,
which profile) and cached on `PlatformConnection.external_account_id` so
each platform only pays that extra lookup once per connection, not once
per post.
"""

from __future__ import annotations

import asyncio
import logging

from composio_client import Composio
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.social_media_analyzer.oauth_providers import (
    get_post_tool_slug,
    is_platform_configured,
    is_publishing_configured,
)
from app.config import settings
from app.db.models import PlatformConnection

logger = logging.getLogger(__name__)


class PublishNotConfiguredError(Exception):
    """Raised when COMPOSIO_API_KEY or this platform's post tool slug
    isn't set — the caller maps this to a 409, same pattern `authorize()`
    already uses for the connection flow."""


class PublishIdentityUnresolvedError(Exception):
    """Raised when a platform's post requires an account identifier
    (Facebook page id, LinkedIn author URN) beyond the connected-account
    id itself, and it couldn't be resolved — most likely the connected
    account genuinely has no accessible page (Facebook) or the identity
    call failed. Reconnecting is the user-facing fix in either case."""


class InstagramMediaRequiredError(Exception):
    """Instagram's real API has no text-only post at all — confirmed live
    against Composio's real Instagram toolkit (only
    INSTAGRAM_CREATE_MEDIA_CONTAINER + INSTAGRAM_CREATE_POST exist, the
    standard Meta Graph API two-step container-then-publish flow, and
    both require an image/video). Raised instead of attempting the call
    at all when `media_url` is missing, rather than letting a real
    Composio 400 surface a confusing/technical error."""


class DeleteNotSupportedError(Exception):
    """Raised when a platform has no real delete capability at all,
    confirmed against Composio's real toolkit rather than assumed —
    Instagram specifically: no delete-media action exists anywhere in its
    toolkit (Meta's Graph API has none for this integration type), unlike
    Facebook/LinkedIn which both have a real, confirmed delete tool."""


# Which real Composio tool deletes a post on each platform, confirmed
# live against each toolkit's catalog — not every platform this app can
# publish to can also delete (Instagram genuinely can't, see
# DeleteNotSupportedError above).
_DELETE_TOOL_SLUG_BY_PLATFORM: dict[str, str] = {
    # The modern Posts API endpoint, supports both ugcPost and share URN
    # formats — matches what publish_post's own x_restli_id extraction
    # already stores (e.g. "urn:li:share:7493009415151738880").
    "linkedin": "LINKEDIN_DELETE_POST",
    "facebook": "FACEBOOK_DELETE_POST",
}

# The JSON argument name each delete tool expects for the post's id —
# confirmed against each tool's real schema, not assumed (they differ:
# LinkedIn's is post_urn, Facebook's is post_id).
_DELETE_ID_ARG_BY_PLATFORM: dict[str, str] = {
    "linkedin": "post_urn",
    "facebook": "post_id",
}


async def delete_post(connection: PlatformConnection, execution_id: str) -> None:
    """Deletes a previously published post from its real platform, using
    the same execution id `publish_post`'s caller already has on file
    (`PublishAttempt.composio_execution_id`). Raises
    `DeleteNotSupportedError` if the platform has no real delete
    capability; any other failure (a real Composio/platform-side error —
    already deleted, missing permission, expired token) propagates as-is
    so the caller can show the real reason."""
    platform = connection.platform
    tool_slug = _DELETE_TOOL_SLUG_BY_PLATFORM.get(platform)
    if tool_slug is None:
        raise DeleteNotSupportedError(
            f"{platform.capitalize()} doesn't support deleting a post through this "
            f"app — delete it directly on {platform.capitalize()} instead."
        )

    client = _client()
    id_arg = _DELETE_ID_ARG_BY_PLATFORM[platform]

    def _execute():
        return client.tools.execute(
            tool_slug,
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={id_arg: execution_id},
        )

    await asyncio.to_thread(_execute)


async def get_post_url(connection: PlatformConnection, execution_id: str) -> str | None:
    """A real, clickable URL to the just-published post, so a "Published"
    confirmation can actually link to it instead of just naming the
    platform. Best-effort by design (never raises) — a failed lookup here
    shouldn't turn a genuinely successful publish into an error; the
    caller just shows the confirmation text without a link. Verified per
    platform, not guessed uniformly:
    - LinkedIn has no permalink field in any of its own API responses —
      confirmed against `LINKEDIN_GET_POST_CONTENT`'s real output schema.
      `https://www.linkedin.com/feed/update/{urn}/` is LinkedIn's own
      long-standing, documented permalink convention for a share URN
      (the same format LinkedIn's own share/embed UI generates), not a
      Composio-specific thing.
    - Facebook's `permalink_url` comes directly from a real
      `FACEBOOK_GET_POST` call — deliberately NOT constructed by hand:
      confirmed live that it does *not* simply combine as
      `facebook.com/{post_id}` (the actual permalink's leading numeric
      segment differs from the page id embedded in `post_id`).
    - Instagram's `permalink` likewise comes from a real
      `INSTAGRAM_GET_IG_MEDIA` call — Instagram's public URL uses a short
      code that isn't derivable from the numeric media id at all.
    - YouTube isn't handled here — see `youtube_upload.get_video_url`,
      which needs no extra API call at all (a stable, well-known URL
      shape, unlike the three above).
    """
    platform = connection.platform
    try:
        if platform == "linkedin":
            return f"https://www.linkedin.com/feed/update/{execution_id}/"

        if platform == "facebook":
            client = _client()

            def _get_post():
                return client.tools.execute(
                    "FACEBOOK_GET_POST",
                    connected_account_id=connection.composio_connected_account_id,
                    user_id=str(connection.company_id),
                    arguments={"post_id": execution_id},
                )

            response = await asyncio.to_thread(_get_post)
            data = getattr(response, "data", None) or {}
            url = data.get("permalink_url") if isinstance(data, dict) else None
            return str(url) if url else None

        if platform == "instagram":
            client = _client()

            def _get_media():
                return client.tools.execute(
                    "INSTAGRAM_GET_IG_MEDIA",
                    connected_account_id=connection.composio_connected_account_id,
                    user_id=str(connection.company_id),
                    arguments={"ig_media_id": execution_id},
                )

            response = await asyncio.to_thread(_get_media)
            data = getattr(response, "data", None) or {}
            url = data.get("permalink") if isinstance(data, dict) else None
            return str(url) if url else None
    except Exception:
        logger.exception("Couldn't resolve a real post URL for %s execution %s", platform, execution_id)
    return None


def _client() -> Composio:
    return Composio(api_key=settings.COMPOSIO_API_KEY)


def _extract_response_id(response: object) -> str:
    """The real post/execution identifier from Composio's response, not
    the whole object. Every tool's real response nests it under `.data`,
    never a flat top-level `.id` on `response` itself (confirmed live —
    the previous `getattr(response, "id", None) or getattr(response,
    "data", response)` fallback found neither, since `response.id`
    doesn't exist, and silently fell through to stringifying the *entire*
    `.data` dict, producing a stored id like `"{'id':
    '2109922212367336_1460783426082148'}"` instead of the real id — a
    real post that genuinely went out, confirmed live via Facebook's own
    Graph API, just recorded under a useless key). Checked in this order
    because the exact field name differs per platform, confirmed against
    each tool's real output schema (`client.tools.retrieve`), not
    assumed: `post_id` is Facebook's own full page+post composite id on a
    *photo* post (more useful than the bare photo id alongside it);
    `x_restli_id` is LinkedIn's actual required response field, not `id`
    (which exists on that same response but isn't guaranteed present);
    `id` covers Facebook's plain text-post response and anything else
    simple. Falls back to a truncated stringification only if none of
    these are present, so a genuinely new/unexpected shape degrades
    instead of crashing."""
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        for key in ("post_id", "x_restli_id", "id"):
            value = data.get(key)
            if value:
                return str(value)
        return str(data)[:128]
    top_level_id = getattr(response, "id", None)
    if top_level_id:
        return str(top_level_id)
    return str(data if data is not None else response)[:128]


# Which JSON field each platform's post tool calls the actual post text —
# confirmed against the real tool schemas (`client.tools.retrieve(slug)`),
# not assumed. Anything not listed here keeps the original "text" default,
# which isn't actually confirmed correct for any currently-configurable
# platform; kept as a fallback rather than raising, so a newly-added
# platform doesn't hard-fail before anyone's checked its real schema —
# same "degrade, don't crash" stance as the rest of this file.
_TEXT_FIELD_BY_PLATFORM: dict[str, str] = {
    "facebook": "message",
    "linkedin": "commentary",
}


async def _resolve_facebook_page_id(
    client: Composio, connected_account_id: str, company_id: str
) -> str | None:
    """Unverified against a live response as of this writing — no
    Facebook account has been connected in this environment (checked via
    `connected_accounts.list()`). Parsing is deliberately defensive
    (multiple candidate keys) rather than a single assumed path, and the
    raw response is logged so a real mismatch is diagnosable, not silent,
    the moment a real account is connected."""

    def _list_pages():
        return client.tools.execute(
            "FACEBOOK_LIST_MANAGED_PAGES",
            connected_account_id=connected_account_id,
            # Same requirement as the main publish call below (confirmed
            # live, the hard way, via a real 400: "User ID is required
            # with connected account", code 1811) — this identity-resolver
            # call is a *separate* tools.execute() and was missed the
            # first time the fix went in, which is exactly what surfaced
            # this same error again on a real LinkedIn/Facebook publish
            # whose identity hadn't been resolved yet.
            user_id=company_id,
            arguments={},
        )

    response = await asyncio.to_thread(_list_pages)
    data = getattr(response, "data", None) or {}
    pages = data.get("data") if isinstance(data, dict) else None
    if pages is None and isinstance(data, list):
        pages = data
    if not pages:
        logger.warning("FACEBOOK_LIST_MANAGED_PAGES returned no managed pages: %r", data)
        return None
    first = pages[0]
    page_id = first.get("id") or first.get("page_id") if isinstance(first, dict) else None
    if not page_id:
        logger.warning("Couldn't find a page id in FACEBOOK_LIST_MANAGED_PAGES's response: %r", first)
    return page_id


async def _resolve_linkedin_author_urn(
    client: Composio, connected_account_id: str, company_id: str
) -> str | None:
    """Same unverified-until-a-real-connection caveat as the Facebook
    resolver above — no LinkedIn account has been connected in this
    environment yet either."""

    def _get_info():
        return client.tools.execute(
            "LINKEDIN_GET_MY_INFO",
            connected_account_id=connected_account_id,
            # See _resolve_facebook_page_id's comment — same missed spot,
            # same real 400 (code 1811) confirmed live on an actual
            # LinkedIn publish attempt.
            user_id=company_id,
            arguments={},
        )

    response = await asyncio.to_thread(_get_info)
    data = getattr(response, "data", None) or {}
    raw_id = data.get("sub") or data.get("id") or data.get("urn") if isinstance(data, dict) else None
    if not raw_id:
        logger.warning("Couldn't find an author id in LINKEDIN_GET_MY_INFO's response: %r", data)
        return None
    return raw_id if str(raw_id).startswith("urn:") else f"urn:li:person:{raw_id}"


async def _resolve_instagram_ig_user_id(
    client: Composio, connected_account_id: str, company_id: str
) -> str | None:
    """The numeric Instagram Business Account id both
    INSTAGRAM_CREATE_MEDIA_CONTAINER and INSTAGRAM_CREATE_POST need as
    `ig_user_id` — resolved via INSTAGRAM_GET_USER_INFO(ig_user_id="me"),
    confirmed live against Composio's real tool catalog/schema
    (`client.tools.retrieve`), same verification discipline as every
    other resolver in this file."""

    def _get_info():
        return client.tools.execute(
            "INSTAGRAM_GET_USER_INFO",
            connected_account_id=connected_account_id,
            user_id=company_id,
            arguments={},
        )

    response = await asyncio.to_thread(_get_info)
    data = getattr(response, "data", None) or {}
    ig_user_id = data.get("id") if isinstance(data, dict) else None
    if not ig_user_id:
        logger.warning("Couldn't find an id in INSTAGRAM_GET_USER_INFO's response: %r", data)
    return ig_user_id


# Platforms whose post tool needs an identifier beyond the connected
# account id itself, and how to resolve it.
_IDENTITY_RESOLVERS = {
    "facebook": _resolve_facebook_page_id,
    "linkedin": _resolve_linkedin_author_urn,
    "instagram": _resolve_instagram_ig_user_id,
}


async def _resolve_identity(
    session: AsyncSession, connection: PlatformConnection, client: Composio
) -> str | None:
    """`connection.external_account_id`, resolving and caching it on the
    row first if unset. `session.add` without `commit` — the caller
    (`publish_post`'s own caller) already commits after logging the
    `PublishAttempt`, so this rides along on that same commit rather than
    needing its own."""
    if connection.external_account_id:
        return connection.external_account_id
    resolver = _IDENTITY_RESOLVERS.get(connection.platform)
    if resolver is None:
        return None
    identity = await resolver(
        client, connection.composio_connected_account_id, str(connection.company_id)
    )
    if identity:
        connection.external_account_id = identity
        session.add(connection)
    return identity


async def _publish_instagram_post(
    session: AsyncSession, connection: PlatformConnection, text: str, media_url: str | None
) -> str:
    """Instagram's own two-step publish flow — a real Meta Graph API
    requirement, not this app's choice: create a media container (the
    caption + image/video URL), then publish that container by id.
    Neither tool slug is settings-driven like other platforms'
    `post_tool_slug` — both are hardcoded here since they're already
    confirmed real against Composio's live catalog, same reasoning as
    `youtube_upload.py` hardcoding `YOUTUBE_MULTIPART_UPLOAD_VIDEO`.
    Images only for now — video/Reels would need container-status polling
    before publishing, not implemented here."""
    if not is_platform_configured("instagram"):
        logger.warning(
            "instagram publishing isn't configured (COMPOSIO_API_KEY / its auth "
            "config id missing in .env)"
        )
        raise PublishNotConfiguredError(
            "Instagram publishing isn't set up yet — ask whoever manages this "
            "workspace to finish connecting it."
        )
    if not media_url:
        raise InstagramMediaRequiredError(
            "This post needs an image or video attached before it can go to "
            "Instagram — attach one, then try publishing again."
        )

    client = _client()
    ig_user_id = await _resolve_identity(session, connection, client)
    if not ig_user_id:
        raise PublishIdentityUnresolvedError(
            "Couldn't resolve the Instagram account this post needs — try "
            "reconnecting Instagram from Integrations."
        )

    def _create_container():
        return client.tools.execute(
            "INSTAGRAM_CREATE_MEDIA_CONTAINER",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={"ig_user_id": ig_user_id, "image_url": media_url, "caption": text},
        )

    container_response = await asyncio.to_thread(_create_container)
    container_data = getattr(container_response, "data", None) or {}
    creation_id = container_data.get("id") if isinstance(container_data, dict) else None
    if not creation_id:
        raise ValueError(f"Instagram didn't return a media container id: {container_data!r}")

    def _publish_container():
        return client.tools.execute(
            "INSTAGRAM_CREATE_POST",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={"ig_user_id": ig_user_id, "creation_id": creation_id},
        )

    publish_response = await asyncio.to_thread(_publish_container)
    return _extract_response_id(publish_response)


async def _publish_facebook_photo_post(
    session: AsyncSession, connection: PlatformConnection, text: str, media_url: str
) -> str:
    """A Facebook post with an actual photo attached — a different tool
    (FACEBOOK_CREATE_PHOTO_POST) from the plain text one, confirmed live
    against Composio's real Facebook toolkit/schema. Takes the image as a
    public URL directly (`url`) — this app's own Supabase Storage URLs
    already are one, no presigned-upload dance needed unlike YouTube/
    Instagram's flows."""
    if not is_platform_configured("facebook"):
        logger.warning(
            "facebook publishing isn't configured (COMPOSIO_API_KEY / its auth "
            "config id missing in .env)"
        )
        raise PublishNotConfiguredError(
            "Facebook publishing isn't set up yet — ask whoever manages this "
            "workspace to finish connecting it."
        )

    client = _client()
    page_id = await _resolve_identity(session, connection, client)
    if not page_id:
        raise PublishIdentityUnresolvedError(
            "Couldn't resolve the Facebook page this post needs — try "
            "reconnecting Facebook from Integrations."
        )

    def _execute():
        return client.tools.execute(
            "FACEBOOK_CREATE_PHOTO_POST",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={"url": media_url, "message": text, "page_id": page_id, "published": True},
        )

    response = await asyncio.to_thread(_execute)
    return _extract_response_id(response)


async def publish_post(
    session: AsyncSession,
    connection: PlatformConnection,
    text: str,
    media_url: str | None = None,
) -> str:
    """Executes `connection.platform`'s configured "create a post" tool
    against its connected account. Returns Composio's execution id on
    success. Raises `PublishNotConfiguredError` if not configured,
    `PublishIdentityUnresolvedError` if the platform needs an identifier
    (page/author) that couldn't be resolved, or `InstagramMediaRequiredError`
    if publishing to Instagram without `media_url` set; any other failure
    (a real Composio/platform-side error) propagates as-is so the caller
    can log the real reason rather than a swallowed generic failure."""
    platform = connection.platform

    # Instagram's shape is fundamentally different from every other
    # platform here (a required two-step flow, no text-only post at all)
    # — same reason YouTube uploads live in their own module rather than
    # being forced into this generic single-call shape.
    if platform == "instagram":
        return await _publish_instagram_post(session, connection, text, media_url)

    # Facebook *does* have a genuine text-only post (unlike Instagram),
    # but FACEBOOK_CREATE_POST — used below for that case — has no image
    # parameter at all; an attached image silently never made it into the
    # post. Confirmed live: a real post went out with the caption but no
    # photo, even though the draft clearly had one attached. A real photo
    # needs FACEBOOK_CREATE_PHOTO_POST instead, a different tool.
    if platform == "facebook" and media_url:
        return await _publish_facebook_photo_post(session, connection, text, media_url)

    if not is_publishing_configured(platform):
        # User-safe message — this often surfaces directly in chat to
        # whoever's using the app, not just an admin, so it must never
        # name internal env vars/config files. The specific missing piece
        # goes to the log instead.
        logger.warning(
            "%s publishing isn't configured (COMPOSIO_API_KEY / its post tool slug "
            "missing in .env)",
            platform,
        )
        raise PublishNotConfiguredError(
            f"{platform.capitalize()} publishing isn't set up yet — ask whoever "
            "manages this workspace to finish connecting it."
        )

    tool_slug = get_post_tool_slug(platform)
    client = _client()

    arguments: dict = {_TEXT_FIELD_BY_PLATFORM.get(platform, "text"): text}

    if platform in _IDENTITY_RESOLVERS:
        identity = await _resolve_identity(session, connection, client)
        if not identity:
            raise PublishIdentityUnresolvedError(
                f"Couldn't resolve the {platform} account identifier this post needs "
                f"(page id / author URN) — try reconnecting {platform} from Integrations."
            )
        if platform == "facebook":
            arguments["page_id"] = identity
        elif platform == "linkedin":
            arguments["author"] = identity

    def _execute():
        return client.tools.execute(
            tool_slug,
            connected_account_id=connection.composio_connected_account_id,
            # Confirmed live (via the YouTube video upload path, which
            # shares this same tools.execute call shape): without this,
            # Composio 400s with "User ID is required with connected
            # account" — connected_account_id alone isn't sufficient. Same
            # identifier this app registers the connection under in the
            # first place (oauth_flow.py's initiate_connection).
            user_id=str(connection.company_id),
            arguments=arguments,
        )

    response = await asyncio.to_thread(_execute)
    return _extract_response_id(response)
