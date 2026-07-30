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
    # `is_global` is the stdlib's own "allocated for public networks" flag
    # — it already excludes RFC1918/ULA private ranges, loopback,
    # link-local (169.254.0.0/16, the cloud metadata range, and fe80::/10),
    # and CGN shared space (100.64.0.0/10), and correctly allows legitimate
    # globally-routable addresses like NAT64-synthesized IPv6
    # (64:ff9b::/96) that a hand-rolled `is_private`/`is_loopback`/
    # `is_link_local`/`is_reserved` combination incorrectly rejected (that
    # combination used `is_reserved`, which is far broader than "unsafe for
    # SSRF purposes" and flagged real public addresses as unsafe — caught
    # live when a real, public, IPv4-only site resolved to a NAT64 address
    # in this environment and got wrongly refused). Multicast isn't
    # excluded by `is_global`, so it's checked separately.
    return ip.is_global and not ip.is_multicast


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
