"""SSRF protection for outbound requests the server makes on a user's behalf.

Any endpoint that fetches a user-supplied URL (currently: company/competitor
onboarding) needs to reject requests to private/internal/cloud-metadata
addresses — otherwise an unauthenticated caller can make this server probe
its own internal network. Not agent-specific, so it lives at the app level
rather than under `agents/company_analyzer/`.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrlError(Exception):
    """Raised when a URL resolves to a disallowed scheme or address."""


def _resolve_ips(hostname: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve hostname: {hostname}") from exc

    ips: set[ipaddress._BaseAddress] = set()
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ips.add(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue
    return list(ips)


def _is_public_ip(ip: ipaddress._BaseAddress) -> bool:
    # Covers RFC1918 private ranges, loopback (127.0.0.0/8, ::1),
    # link-local (169.254.0.0/16 — this is the cloud metadata range on
    # AWS/GCP/Azure — and fe80::/10), multicast, and other IANA-reserved
    # blocks. Deliberately conservative: anything not obviously public is
    # rejected.
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> None:
    """Raise `UnsafeUrlError` unless `url` is http(s) and every address its
    hostname resolves to is public. Synchronous — DNS resolution is fast
    enough that callers doing this per-request should run it via
    `asyncio.to_thread` to avoid blocking the event loop."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"Disallowed URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname")

    ips = _resolve_ips(parsed.hostname)
    if not ips:
        raise UnsafeUrlError(f"Hostname resolved to no usable addresses: {parsed.hostname}")
    if not all(_is_public_ip(ip) for ip in ips):
        raise UnsafeUrlError(f"URL resolves to a private/internal address: {parsed.hostname}")
