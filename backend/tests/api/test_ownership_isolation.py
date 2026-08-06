"""Cross-tenant isolation through the real HTTP surface.

Every other API test file stubs one fixed signed-in user, so none of them
can catch "user B can read user A's data" — that's what this file is for.
The dependency override here is switchable mid-test, which is what lets a
single app instance answer as two different people.

Coverage is deliberately one route per endpoint family rather than all of
them: the check is the same shared `ensure_company_access` call
everywhere, so the risk being tested is "a family was missed entirely",
not "one route in a family behaves differently".
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import companies as companies_module
from app.api.v1.endpoints import content_management as cm_module
from app.api.v1.endpoints import dashboard as dashboard_module
from app.api.v1.endpoints import knowledge_base as kb_module
from app.api.v1.endpoints import media_library as media_module
from app.api.v1.endpoints import social_media_analyzer as social_module
from app.api.v1.endpoints import trends as trends_module
from app.db.models import (
    Company,
    CompanyMember,
    ContentItem,
    ContentPlan,
    Document,
    MediaAsset,
    PlatformConnection,
    Strategy,
    TrendReport,
)
from app.db.session import get_session
from app.security.auth import CurrentUser, get_current_user

USER_A = CurrentUser(id="user-a", email="a@example.com")
USER_B = CurrentUser(id="user-b", email="b@example.com")


class _Signer:
    """Mutable holder so a test can switch which user the app sees."""

    def __init__(self) -> None:
        self.user = USER_A

    def __call__(self) -> CurrentUser:
        return self.user


@pytest_asyncio.fixture
async def signer():
    return _Signer()


@pytest_asyncio.fixture
async def owned_by_a(test_session_factory):
    """One company owned outright by user A, populated with one row of
    every company-scoped type so each endpoint family has something real
    to refuse user B access to."""
    ids = {
        "company": uuid.uuid4(),
        "strategy": uuid.uuid4(),
        "plan": uuid.uuid4(),
        "item": uuid.uuid4(),
        "document": uuid.uuid4(),
        "asset": uuid.uuid4(),
        "connection": uuid.uuid4(),
        "report": uuid.uuid4(),
    }
    async with test_session_factory() as session:
        session.add(Company(id=ids["company"], url="https://a.example.com", status="complete"))
        session.add(
            CompanyMember(company_id=ids["company"], user_id=USER_A.id, role="owner")
        )
        session.add(
            Strategy(id=ids["strategy"], company_id=ids["company"], status="complete")
        )
        session.add(ContentPlan(id=ids["plan"], company_id=ids["company"], status="complete"))
        session.add(
            ContentItem(
                id=ids["item"],
                content_plan_id=ids["plan"],
                title="A's secret post",
                description="Private.",
                content_type="post",
                platform="instagram",
                suggested_date=date(2026, 8, 5),
                approval_status="pending",
            )
        )
        session.add(
            Document(
                id=ids["document"],
                company_id=ids["company"],
                source_type="website",
                source_url="https://a.example.com/about",
                chunk_index=0,
                content="A's private content.",
            )
        )
        session.add(
            MediaAsset(
                id=ids["asset"],
                company_id=ids["company"],
                filename="a.png",
                content_type="image/png",
                size_bytes=1,
                storage_path="a/a.png",
            )
        )
        session.add(
            PlatformConnection(
                id=ids["connection"],
                company_id=ids["company"],
                platform="instagram",
                status="connected",
                composio_connected_account_id="ca_a",
            )
        )
        session.add(
            TrendReport(
                id=ids["report"],
                company_id=ids["company"],
                status="complete",
                period_days=7,
            )
        )
        await session.commit()
    return ids


def _build(module, test_session_factory, signer) -> AsyncClient:
    app = FastAPI()
    app.include_router(module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = signer
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_user_b_cannot_read_user_as_company(test_session_factory, signer, owned_by_a):
    async with _build(companies_module, test_session_factory, signer) as client:
        signer.user = USER_A
        assert (await client.get(f"/{owned_by_a['company']}")).status_code == 200

        signer.user = USER_B
        response = await client.get(f"/{owned_by_a['company']}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Company not found"


async def test_user_b_does_not_see_user_as_company_in_the_list(
    test_session_factory, signer, owned_by_a
):
    async with _build(companies_module, test_session_factory, signer) as client:
        signer.user = USER_B
        body = (await client.get("/")).json()
        assert body["items"] == []
        # `total` is filtered too — an unfiltered count would leak how many
        # other tenants exist even with the rows themselves hidden.
        assert body["total"] == 0


async def test_user_b_cannot_hijack_a_company_by_reonboarding_its_url(
    monkeypatch, test_session_factory, signer, owned_by_a
):
    """POST /companies with an existing URL takes the re-onboard branch,
    which wipes documents and restarts onboarding — without an ownership
    check that's a hijack needing no company id at all."""
    async def _noop(company_id, url):
        pass

    monkeypatch.setattr(companies_module, "run_onboarding", _noop)

    async with _build(companies_module, test_session_factory, signer) as client:
        signer.user = USER_B
        response = await client.post("/", json={"url": "https://a.example.com"})
        assert response.status_code == 404

    # A's document survived.
    async with test_session_factory() as session:
        assert await session.get(Document, owned_by_a["document"]) is not None


async def test_creating_a_company_records_the_creator_as_owner(
    monkeypatch, test_session_factory, signer
):
    async def _noop(company_id, url):
        pass

    monkeypatch.setattr(companies_module, "run_onboarding", _noop)

    async with _build(companies_module, test_session_factory, signer) as client:
        signer.user = USER_A
        created = (await client.post("/", json={"url": "https://new.example.com"})).json()

        # B never sees it, so ownership was recorded at creation rather
        # than left to claim-on-first-access.
        signer.user = USER_B
        assert (await client.get(f"/{created['id']}")).status_code == 404


async def test_user_b_cannot_read_or_mutate_user_as_content(
    test_session_factory, signer, owned_by_a
):
    async with _build(cm_module, test_session_factory, signer) as client:
        signer.user = USER_B

        assert (await client.get(f"/strategies/{owned_by_a['strategy']}")).status_code == 404
        assert (await client.get(f"/content-plans/{owned_by_a['plan']}")).status_code == 404
        assert (
            await client.patch(
                f"/content-items/{owned_by_a['item']}", json={"approval_status": "approved"}
            )
        ).status_code == 404
        assert (
            await client.get(f"/content-items/{owned_by_a['item']}/revisions")
        ).status_code == 404

        # Cross-company lists are filtered, not just per-row guarded.
        assert (await client.get("/content-items")).json()["items"] == []
        assert (await client.get("/approvals/pending")).json()["items"] == []
        assert (await client.get("/strategies")).json()["total"] == 0


async def test_user_as_approval_is_still_untouched_after_bs_attempt(
    test_session_factory, signer, owned_by_a
):
    async with _build(cm_module, test_session_factory, signer) as client:
        signer.user = USER_B
        await client.patch(
            f"/content-items/{owned_by_a['item']}", json={"approval_status": "approved"}
        )

    async with test_session_factory() as session:
        item = await session.get(ContentItem, owned_by_a["item"])
        assert item.approval_status == "pending"


async def test_user_b_cannot_reach_user_as_knowledge_base(
    test_session_factory, signer, owned_by_a
):
    async with _build(kb_module, test_session_factory, signer) as client:
        signer.user = USER_B
        assert (await client.get(f"/documents/{owned_by_a['document']}")).status_code == 404
        assert (
            await client.delete(f"/documents/{owned_by_a['document']}")
        ).status_code == 404
        assert (
            await client.get("/documents", params={"company_id": str(owned_by_a["company"])})
        ).status_code == 404
        assert (
            await client.get("/freshness", params={"company_id": str(owned_by_a["company"])})
        ).status_code == 404


async def test_user_b_cannot_reach_user_as_media(test_session_factory, signer, owned_by_a):
    async with _build(media_module, test_session_factory, signer) as client:
        signer.user = USER_B
        assert (
            await client.get(f"/{owned_by_a['company']}/assets")
        ).status_code == 404
        assert (await client.delete(f"/assets/{owned_by_a['asset']}")).status_code == 404


async def test_user_b_cannot_touch_user_as_platform_connections(
    test_session_factory, signer, owned_by_a
):
    """The highest-stakes family: a connection is a live handle on someone
    else's social account."""
    async with _build(social_module, test_session_factory, signer) as client:
        signer.user = USER_B
        assert (
            await client.get("/connections", params={"company_id": str(owned_by_a["company"])})
        ).status_code == 404
        assert (
            await client.delete(f"/connections/{owned_by_a['connection']}")
        ).status_code == 404
        assert (
            await client.get(f"/connections/{owned_by_a['connection']}/metrics")
        ).status_code == 404
        assert (
            await client.get(
                "/connections/instagram/authorize",
                params={"company_id": str(owned_by_a["company"])},
            )
        ).status_code == 404
        assert (await client.get("/publish-attempts")).json()["items"] == []

    # The connection wasn't disconnected by the refused DELETE.
    async with test_session_factory() as session:
        connection = await session.get(PlatformConnection, owned_by_a["connection"])
        assert connection.status == "connected"
        assert connection.composio_connected_account_id == "ca_a"


async def test_user_b_cannot_reach_user_as_trend_reports(
    test_session_factory, signer, owned_by_a
):
    async with _build(trends_module, test_session_factory, signer) as client:
        signer.user = USER_B
        assert (await client.get(f"/reports/{owned_by_a['report']}")).status_code == 404
        assert (await client.get("/reports")).json()["total"] == 0
        assert (
            await client.post(
                "/opportunities", params={"company_id": str(owned_by_a["company"])}
            )
        ).status_code == 404


async def test_dashboard_counts_only_the_callers_own_companies(
    test_session_factory, signer, owned_by_a
):
    async with _build(dashboard_module, test_session_factory, signer) as client:
        signer.user = USER_A
        assert (await client.get("/summary")).json()["company_count"] == 1

        signer.user = USER_B
        body = (await client.get("/summary")).json()
        assert body["company_count"] == 0
        assert body["recent_companies"] == []


async def test_an_invited_teammate_gets_full_access(test_session_factory, signer, owned_by_a):
    """The other half of isolation: invites actually work. B is refused,
    is invited by A, and then sees exactly what A sees."""
    async with _build(companies_module, test_session_factory, signer) as client:
        signer.user = USER_B
        assert (await client.get(f"/{owned_by_a['company']}")).status_code == 404

        signer.user = USER_A
        invited = await client.post(
            f"/{owned_by_a['company']}/members", json={"email": USER_B.email}
        )
        assert invited.status_code == 201
        assert invited.json()["user_id"] is None  # inert until B signs in

        signer.user = USER_B
        assert (await client.get(f"/{owned_by_a['company']}")).status_code == 200

        members = (await client.get(f"/{owned_by_a['company']}/members")).json()
        assert members["current_user_id"] == USER_B.id
        assert {m["user_id"] for m in members["items"]} == {USER_A.id, USER_B.id}

    # And the invited teammate can now act on the company's content.
    async with _build(cm_module, test_session_factory, signer) as client:
        signer.user = USER_B
        assert (await client.get(f"/strategies/{owned_by_a['strategy']}")).status_code == 200


async def test_removing_the_last_member_is_refused(test_session_factory, signer, owned_by_a):
    """Otherwise the company silently returns to "unclaimed" — visible to
    every signed-in user again, undoing the whole feature."""
    async with _build(companies_module, test_session_factory, signer) as client:
        signer.user = USER_A
        members = (await client.get(f"/{owned_by_a['company']}/members")).json()["items"]
        only = next(m for m in members if m["user_id"] == USER_A.id)

        response = await client.delete(f"/{owned_by_a['company']}/members/{only['id']}")
        assert response.status_code == 409

        signer.user = USER_B
        assert (await client.get(f"/{owned_by_a['company']}")).status_code == 404


async def test_inviting_the_same_email_twice_is_refused(
    test_session_factory, signer, owned_by_a
):
    async with _build(companies_module, test_session_factory, signer) as client:
        signer.user = USER_A
        first = await client.post(
            f"/{owned_by_a['company']}/members", json={"email": "c@example.com"}
        )
        assert first.status_code == 201
        second = await client.post(
            f"/{owned_by_a['company']}/members", json={"email": "C@Example.com"}
        )
        assert second.status_code == 409


async def test_user_b_cannot_invite_themselves_to_user_as_company(
    test_session_factory, signer, owned_by_a
):
    async with _build(companies_module, test_session_factory, signer) as client:
        signer.user = USER_B
        response = await client.post(
            f"/{owned_by_a['company']}/members", json={"email": USER_B.email}
        )
        assert response.status_code == 404
