"""Tests for the Composio-brokered connection flow."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.agents.social_media_analyzer import oauth_flow


def _configure(monkeypatch, **platform_ids):
    monkeypatch.setattr(oauth_flow.settings, "COMPOSIO_API_KEY", "test-composio-key")
    for setting_name, value in platform_ids.items():
        monkeypatch.setattr(oauth_flow.settings, setting_name, value)


def test_map_status_covers_every_known_composio_status():
    assert oauth_flow.map_status("ACTIVE") == "connected"
    assert oauth_flow.map_status("INITIALIZING") == "pending"
    assert oauth_flow.map_status("INITIATED") == "pending"
    assert oauth_flow.map_status("FAILED") == "error"
    assert oauth_flow.map_status("INACTIVE") == "error"
    assert oauth_flow.map_status("REVOKED") == "error"
    assert oauth_flow.map_status("EXPIRED") == "expired"


def test_map_status_defaults_unknown_values_to_error():
    assert oauth_flow.map_status("SOMETHING_NEW") == "error"


async def test_initiate_connection_raises_when_api_key_not_set(monkeypatch):
    monkeypatch.setattr(oauth_flow.settings, "COMPOSIO_API_KEY", "")

    with pytest.raises(oauth_flow.ComposioNotConfiguredError):
        await oauth_flow.initiate_connection("instagram", uuid.uuid4(), "https://app.example.com/cb")


async def test_initiate_connection_raises_when_auth_config_id_not_set(monkeypatch):
    _configure(monkeypatch, COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID="")

    with pytest.raises(oauth_flow.ComposioNotConfiguredError):
        await oauth_flow.initiate_connection("instagram", uuid.uuid4(), "https://app.example.com/cb")


async def test_initiate_connection_raises_for_unknown_platform(monkeypatch):
    _configure(monkeypatch)

    with pytest.raises(ValueError):
        await oauth_flow.initiate_connection("myspace", uuid.uuid4(), "https://app.example.com/cb")


class _FakeConnectedAccounts:
    def __init__(self, create_result=None, retrieve_result=None, raise_on_delete=False):
        self._create_result = create_result
        self._retrieve_result = retrieve_result
        self._raise_on_delete = raise_on_delete
        self.create_kwargs = None
        self.retrieve_args = None
        self.delete_args = None
        self.delete_kwargs = None

    def create(self, *, auth_config, connection):
        self.create_kwargs = {"auth_config": auth_config, "connection": connection}
        return self._create_result

    def retrieve(self, nanoid):
        self.retrieve_args = nanoid
        return self._retrieve_result

    def delete(self, nanoid, *, revoke_on_delete=False):
        self.delete_args = nanoid
        self.delete_kwargs = {"revoke_on_delete": revoke_on_delete}
        if self._raise_on_delete:
            raise RuntimeError("Composio API error")


async def test_initiate_connection_returns_id_and_redirect_url(monkeypatch):
    _configure(monkeypatch, COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID="ac_instagram_123")

    fake_accounts = _FakeConnectedAccounts(
        create_result=SimpleNamespace(id="ca_abc123", redirect_url="https://composio.dev/auth/xyz")
    )
    monkeypatch.setattr(
        oauth_flow, "_client", lambda: SimpleNamespace(connected_accounts=fake_accounts)
    )

    company_id = uuid.uuid4()
    connected_account_id, redirect_url = await oauth_flow.initiate_connection(
        "instagram", company_id, "https://app.example.com/cb"
    )

    assert connected_account_id == "ca_abc123"
    assert redirect_url == "https://composio.dev/auth/xyz"
    assert fake_accounts.create_kwargs["auth_config"] == {"id": "ac_instagram_123"}
    assert fake_accounts.create_kwargs["connection"] == {
        "user_id": str(company_id),
        "callback_url": "https://app.example.com/cb",
    }


async def test_initiate_connection_raises_when_composio_returns_no_redirect_url(monkeypatch):
    _configure(monkeypatch, COMPOSIO_INSTAGRAM_AUTH_CONFIG_ID="ac_instagram_123")

    fake_accounts = _FakeConnectedAccounts(
        create_result=SimpleNamespace(id="ca_abc123", redirect_url=None)
    )
    monkeypatch.setattr(
        oauth_flow, "_client", lambda: SimpleNamespace(connected_accounts=fake_accounts)
    )

    with pytest.raises(oauth_flow.ComposioNotConfiguredError):
        await oauth_flow.initiate_connection("instagram", uuid.uuid4(), "https://app.example.com/cb")


async def test_get_connection_status_maps_composio_status(monkeypatch):
    fake_accounts = _FakeConnectedAccounts(retrieve_result=SimpleNamespace(status="ACTIVE"))
    monkeypatch.setattr(
        oauth_flow, "_client", lambda: SimpleNamespace(connected_accounts=fake_accounts)
    )

    status = await oauth_flow.get_connection_status("ca_abc123")

    assert status == "connected"
    assert fake_accounts.retrieve_args == "ca_abc123"


async def test_get_connection_status_returns_error_on_api_failure(monkeypatch):
    class _FailingAccounts:
        def retrieve(self, nanoid):
            raise RuntimeError("Composio API error")

    monkeypatch.setattr(
        oauth_flow, "_client", lambda: SimpleNamespace(connected_accounts=_FailingAccounts())
    )

    status = await oauth_flow.get_connection_status("ca_abc123")

    assert status == "error"


async def test_disconnect_connection_calls_delete_with_revoke(monkeypatch):
    fake_accounts = _FakeConnectedAccounts()
    monkeypatch.setattr(
        oauth_flow, "_client", lambda: SimpleNamespace(connected_accounts=fake_accounts)
    )

    await oauth_flow.disconnect_connection("ca_abc123")

    assert fake_accounts.delete_args == "ca_abc123"
    assert fake_accounts.delete_kwargs == {"revoke_on_delete": True}


async def test_disconnect_connection_swallows_api_failure(monkeypatch):
    fake_accounts = _FakeConnectedAccounts(raise_on_delete=True)
    monkeypatch.setattr(
        oauth_flow, "_client", lambda: SimpleNamespace(connected_accounts=fake_accounts)
    )

    # Must not raise — the local row is being cleared regardless.
    await oauth_flow.disconnect_connection("ca_abc123")
