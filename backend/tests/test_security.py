"""Tests for SSRF protection (app/security.py)."""

from __future__ import annotations

import pytest

from app.security import UnsafeUrlError, validate_public_url


def _mock_resolve(monkeypatch, hostname_to_ip: dict[str, list[str]]) -> None:
    def fake_getaddrinfo(hostname, port):
        if hostname not in hostname_to_ip:
            import socket

            raise socket.gaierror("not found")
        return [(None, None, None, None, (ip, 0)) for ip in hostname_to_ip[hostname]]

    monkeypatch.setattr("app.security.socket.getaddrinfo", fake_getaddrinfo)


def test_rejects_non_http_schemes():
    with pytest.raises(UnsafeUrlError, match="scheme"):
        validate_public_url("ftp://example.com/")
    with pytest.raises(UnsafeUrlError, match="scheme"):
        validate_public_url("file:///etc/passwd")


def test_rejects_url_with_no_hostname():
    with pytest.raises(UnsafeUrlError, match="hostname"):
        validate_public_url("https:///path")


def test_rejects_unresolvable_hostname(monkeypatch):
    _mock_resolve(monkeypatch, {})
    with pytest.raises(UnsafeUrlError, match="resolve"):
        validate_public_url("https://nonexistent.invalid/")


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "169.254.169.254",  # cloud metadata (AWS/GCP/Azure)
        "192.168.1.1",  # RFC1918 private
        "10.0.0.5",  # RFC1918 private
        "172.16.0.1",  # RFC1918 private
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "0.0.0.0",  # unspecified
    ],
)
def test_rejects_private_and_internal_addresses(monkeypatch, ip):
    _mock_resolve(monkeypatch, {"evil.example.com": [ip]})
    with pytest.raises(UnsafeUrlError, match="private/internal"):
        validate_public_url("https://evil.example.com/")


def test_allows_public_addresses(monkeypatch):
    _mock_resolve(monkeypatch, {"example.com": ["93.184.216.34"]})
    validate_public_url("https://example.com/")  # should not raise


def test_rejects_when_any_resolved_address_is_private(monkeypatch):
    # DNS rebinding style: one public, one private address for the same
    # hostname — must reject if *any* resolved address is unsafe.
    _mock_resolve(monkeypatch, {"mixed.example.com": ["93.184.216.34", "127.0.0.1"]})
    with pytest.raises(UnsafeUrlError, match="private/internal"):
        validate_public_url("https://mixed.example.com/")


def test_allows_nat64_synthesized_address_alongside_real_ip(monkeypatch):
    # Caught live: a real, public, IPv4-only site resolved (in an
    # environment with DNS64) to both its real IPv4 address and a
    # synthesized IPv6 address in the NAT64 well-known prefix
    # (64:ff9b::/96, RFC 6052) — a legitimate, globally-routable address,
    # not an internal one. `ipaddress.IPv6Address.is_reserved` is `True`
    # for this prefix (it's in IANA's special-purpose registry) even
    # though it's globally reachable, so a naive `is_reserved` check
    # wrongly rejected the whole hostname. `is_global` correctly allows it.
    _mock_resolve(
        monkeypatch,
        {"nat64.example.com": ["93.184.216.34", "64:ff9b::5db8:d822"]},
    )
    validate_public_url("https://nat64.example.com/")  # should not raise
