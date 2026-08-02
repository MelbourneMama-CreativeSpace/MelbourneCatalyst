"""Content Management routes: generate a Strategy from a company's profile
+ relevant trends, then generate a ContentPlan (calendar) from that.

Both POST endpoints run their LangGraph pipeline synchronously (awaited
inline, not via BackgroundTasks) — a single Claude tool-use call is fast
enough that a plain POST-and-wait is simpler than the fire-and-forget +
poll pattern company onboarding needs for its ~30s scrape+embed pipeline.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.content_management.campaign_graph import run_campaign_generation
from app.agents.content_management.collaboration_graph import run_collaboration_generation
from app.agents.content_management.content_plan_graph import (
    fetch_kb_references,
    format_context,
    regenerate_item_draft_copy,
    run_content_plan_generation,
)
from app.agents.content_management.content_planner import generate_content_item_from_input
from app.agents.content_management.creative_brief import generate_creative_brief
from app.agents.content_management.quality_check import check_content_quality
from app.agents.content_management.repurposing import repurpose_content_item
from app.agents.content_management.strategy_graph import run_strategy_generation
from app.agents.knowledge_base.generated_content_indexing import index_on_approval
from app.db.models import (
    Campaign,
    Collaboration,
    Company,
    ContentItem,
    ContentItemComment,
    ContentItemCreativeBrief,
    ContentItemRevision,
    ContentPlan,
    Strategy,
)
from app.db.session import get_session
from app.models.content_management import (
    CampaignCreateRequest,
    CampaignLifecycleUpdateRequest,
    CampaignListResponse,
    CampaignOut,
    CollaborationCreateRequest,
    CollaborationListResponse,
    CollaborationOut,
    CollaborationSummaryOut,
    ContentItemCommentCreateRequest,
    ContentItemCommentListResponse,
    ContentItemCommentOut,
    ContentItemCreativeBriefOut,
    ContentItemListResponse,
    ContentItemOut,
    ContentItemRepurposeRequest,
    ContentItemRevisionListResponse,
    ContentItemRevisionOut,
    ContentItemUpdateRequest,
    ContentItemWithCompanyOut,
    ScheduleContentItemRequest,
    ContentPlanCreateRequest,
    ContentPlanListResponse,
    ContentPlanOut,
    ContentPlanSummaryOut,
    ManualContentItemCreateRequest,
    PendingApprovalListResponse,
    PendingApprovalOut,
    StrategyApprovalUpdateRequest,
    StrategyCreateRequest,
    StrategyListResponse,
    StrategyOut,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import accessible_company_id_clause, ensure_company_access

router = APIRouter(dependencies=[Depends(get_current_user)])


async def _get_item_and_plan_or_404(
    session: AsyncSession, item_id: uuid.UUID, user: CurrentUser
) -> tuple[ContentItem, ContentPlan]:
    """Resolve a ContentItem *and* prove the caller may act on it.

    A ContentItem has no `company_id` of its own — it reaches its company
    through its ContentPlan, which is why every per-item route here needs
    two lookups rather than one. Centralised so a new item route can't
    accidentally skip the second half.
    """
    item = await session.get(ContentItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    plan = await session.get(ContentPlan, item.content_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    await ensure_company_access(session, plan.company_id, user)
    return item, plan


@router.get("/approvals/pending", response_model=PendingApprovalListResponse)
async def list_pending_approvals(
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> PendingApprovalListResponse:
    """One combined queue for every `pending` Strategy and ContentItem
    across every company the caller belongs to — the "assigned to you"
    surface the sidebar badge and the /approvals page both read from.
    Registered before any catch-all-shaped route in this router (there
    isn't one today, but matches the defensive ordering convention used
    elsewhere in this codebase, e.g. trends.py's /reports vs
    /{trend_id})."""
    strategy_rows = (
        await session.execute(
            select(Strategy, Company.name)
            .join(Company, Strategy.company_id == Company.id)
            .where(
                Strategy.approval_status == "pending",
                accessible_company_id_clause(user, Strategy.company_id),
            )
        )
    ).all()
    content_item_rows = (
        await session.execute(
            select(ContentItem, ContentPlan.company_id, Company.name)
            .join(ContentPlan, ContentItem.content_plan_id == ContentPlan.id)
            .join(Company, ContentPlan.company_id == Company.id)
            .where(
                ContentItem.approval_status == "pending",
                accessible_company_id_clause(user, ContentPlan.company_id),
            )
        )
    ).all()

    items = [
        PendingApprovalOut(
            type="strategy",
            id=strategy.id,
            company_id=strategy.company_id,
            company_name=company_name,
            title=strategy.summary[:120] if strategy.summary else "Strategy pending review",
            reviewer=strategy.reviewer,
            created_at=strategy.created_at,
        )
        for strategy, company_name in strategy_rows
    ] + [
        PendingApprovalOut(
            type="content_item",
            id=item.id,
            company_id=company_id,
            company_name=company_name,
            title=item.title,
            reviewer=item.reviewer,
            created_at=item.created_at,
        )
        for item, company_id, company_name in content_item_rows
    ]
    items.sort(key=lambda i: i.created_at, reverse=True)

    return PendingApprovalListResponse(items=items, total=len(items))


async def _get_ready_company_or_error(
    session: AsyncSession, company_id: uuid.UUID, user: CurrentUser
) -> Company:
    """Ownership check, plus a rejection for companies whose onboarding
    never produced a usable profile — generating a strategy or content
    plan from an all-`Unknown` context wastes a Claude call and silently
    produces low-value output with no clue why to the caller. Ownership
    comes first so the readiness 409 can't be used to probe another
    tenant's onboarding state."""
    company = await ensure_company_access(session, company_id, user)
    if company.status != "complete":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Company profile is not ready (status: {company.status}). "
                "Onboarding must complete successfully before generating content."
            ),
        )
    return company


@router.post("/strategies", response_model=StrategyOut)
async def create_strategy(
    payload: StrategyCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> StrategyOut:
    await _get_ready_company_or_error(session, payload.company_id, user)

    strategy = Strategy(id=uuid.uuid4(), company_id=payload.company_id, status="pending")
    session.add(strategy)
    await session.commit()

    await run_strategy_generation(strategy.id, payload.company_id)

    # populate_existing=True: the graph mutated this row via a *different*
    # session (async_session_factory() inside run_strategy_generation), but
    # this session still has `strategy` cached in its identity map from the
    # insert above (expire_on_commit=False) — without this, a plain re-fetch
    # would silently return the stale pre-generation object instead of
    # hitting the DB for the real current state.
    refreshed = (
        await session.execute(
            select(Strategy)
            .execution_options(populate_existing=True)
            .where(Strategy.id == strategy.id)
        )
    ).scalar_one()
    return StrategyOut.model_validate(refreshed)


@router.get("/strategies", response_model=StrategyListResponse)
async def list_strategies(
    company_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> StrategyListResponse:
    visible = accessible_company_id_clause(user, Strategy.company_id)
    stmt = select(Strategy).where(visible).order_by(Strategy.created_at.desc())
    count_stmt = select(func.count()).select_from(Strategy).where(visible)
    if company_id is not None:
        stmt = stmt.where(Strategy.company_id == company_id)
        count_stmt = count_stmt.where(Strategy.company_id == company_id)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return StrategyListResponse(items=[StrategyOut.model_validate(row) for row in rows], total=total)


@router.get("/strategies/{strategy_id}", response_model=StrategyOut)
async def get_strategy(
    strategy_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> StrategyOut:
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await ensure_company_access(session, strategy.company_id, user)
    return StrategyOut.model_validate(strategy)


@router.patch("/strategies/{strategy_id}/approval", response_model=StrategyOut)
async def update_strategy_approval(
    strategy_id: uuid.UUID,
    payload: StrategyApprovalUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> StrategyOut:
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await ensure_company_access(session, strategy.company_id, user)
    strategy.approval_status = payload.approval_status
    strategy.approved_by = payload.approved_by
    if payload.reviewer is not None:
        strategy.reviewer = payload.reviewer

    if payload.approval_status == "approved":
        content = "\n\n".join(
            filter(
                None,
                [strategy.summary, strategy.marketing_strategy, strategy.campaign_direction],
            )
        )
        await index_on_approval(
            session,
            strategy.company_id,
            "strategy",
            f"strategy://{strategy.id}",
            content,
        )

    await session.commit()
    await session.refresh(strategy)
    return StrategyOut.model_validate(strategy)


@router.post("/content-plans", response_model=ContentPlanOut)
async def create_content_plan(
    payload: ContentPlanCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentPlanOut:
    await _get_ready_company_or_error(session, payload.company_id, user)
    if payload.strategy_id is not None:
        strategy = await session.get(Strategy, payload.strategy_id)
        if strategy is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        if strategy.company_id != payload.company_id:
            raise HTTPException(
                status_code=400, detail="Strategy does not belong to the given company"
            )

    content_plan = ContentPlan(
        id=uuid.uuid4(),
        company_id=payload.company_id,
        strategy_id=payload.strategy_id,
        status="pending",
    )
    session.add(content_plan)
    await session.commit()

    await run_content_plan_generation(
        content_plan.id, payload.company_id, payload.strategy_id, payload.days
    )

    # populate_existing=True — same identity-map staleness reason as
    # create_strategy above: this session's cached `content_plan` still
    # shows status="pending" from before the graph ran it under a
    # different session.
    refreshed = (
        await session.execute(
            select(ContentPlan)
            .options(selectinload(ContentPlan.items))
            .execution_options(populate_existing=True)
            .where(ContentPlan.id == content_plan.id)
        )
    ).scalar_one()
    return ContentPlanOut.model_validate(refreshed)


async def _get_or_create_manual_plan(session: AsyncSession, company_id: uuid.UUID) -> ContentPlan:
    """One reusable `ContentPlan` per company holds every manually-input
    item — `is_manual=True` distinguishes it from AI-generated calendars
    so it never shows up mixed into a real generated plan's items."""
    manual_plan = (
        await session.execute(
            select(ContentPlan).where(
                ContentPlan.company_id == company_id, ContentPlan.is_manual.is_(True)
            )
        )
    ).scalar_one_or_none()
    if manual_plan is not None:
        return manual_plan

    manual_plan = ContentPlan(
        id=uuid.uuid4(), company_id=company_id, status="complete", is_manual=True
    )
    session.add(manual_plan)
    await session.flush()
    return manual_plan


@router.post("/content-plans/{company_id}/manual-item", response_model=ContentItemOut)
async def create_manual_content_item(
    company_id: uuid.UUID,
    payload: ManualContentItemCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemOut:
    """A single user-supplied topic/idea, generated into one ready-to-publish
    item — the manual-input counterpart to the full-calendar `POST
    /content-plans` above. Grounded in the same company profile + KB
    reference-material context as regular generation, so voice stays
    consistent between the two paths."""
    company = await _get_ready_company_or_error(session, company_id, user)
    manual_plan = await _get_or_create_manual_plan(session, company_id)

    kb_references = await fetch_kb_references(session, company_id, payload.topic)
    context = format_context(company, None, [], kb_references)

    generated_item, ok = await generate_content_item_from_input(
        context, payload.topic, payload.platform, payload.content_type
    )
    if not ok or generated_item is None:
        raise HTTPException(
            status_code=502,
            detail=(
                "Content generation failed (check ANTHROPIC_API_KEY / Claude API availability)."
            ),
        )

    item = ContentItem(
        id=uuid.uuid4(),
        content_plan_id=manual_plan.id,
        title=generated_item.title,
        description=generated_item.description,
        content_type=generated_item.content_type,
        platform=generated_item.platform,
        theme=generated_item.theme,
        suggested_date=generated_item.suggested_date,
        draft_copy=generated_item.draft_copy,
        hashtags=generated_item.hashtags,
        approval_status="pending",
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return ContentItemOut.model_validate(item)


@router.get("/content-plans", response_model=ContentPlanListResponse)
async def list_content_plans(
    company_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentPlanListResponse:
    visible = accessible_company_id_clause(user, ContentPlan.company_id)
    stmt = select(ContentPlan).where(visible).order_by(ContentPlan.created_at.desc())
    count_stmt = select(func.count()).select_from(ContentPlan).where(visible)
    if company_id is not None:
        stmt = stmt.where(ContentPlan.company_id == company_id)
        count_stmt = count_stmt.where(ContentPlan.company_id == company_id)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return ContentPlanListResponse(
        items=[ContentPlanSummaryOut.model_validate(row) for row in rows], total=total
    )


@router.get("/content-plans/{content_plan_id}", response_model=ContentPlanOut)
async def get_content_plan(
    content_plan_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentPlanOut:
    content_plan = (
        await session.execute(
            select(ContentPlan)
            .options(selectinload(ContentPlan.items))
            .where(ContentPlan.id == content_plan_id)
        )
    ).scalar_one_or_none()
    if content_plan is None:
        raise HTTPException(status_code=404, detail="Content plan not found")
    await ensure_company_access(session, content_plan.company_id, user)
    return ContentPlanOut.model_validate(content_plan)


@router.get("/content-items", response_model=ContentItemListResponse)
async def list_content_items(
    company_id: uuid.UUID | None = None,
    platform: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemListResponse:
    """Flat list of every content item across the caller's own companies —
    the Draft Workspace's data source, grouped by platform client-side
    rather than viewed one company's calendar at a time.
    `company_id`/`platform` are optional filters."""
    stmt = (
        select(ContentItem, ContentPlan.company_id, Company.name)
        .join(ContentPlan, ContentItem.content_plan_id == ContentPlan.id)
        .join(Company, ContentPlan.company_id == Company.id)
        .where(accessible_company_id_clause(user, ContentPlan.company_id))
        .order_by(ContentItem.suggested_date.desc())
    )
    if company_id is not None:
        stmt = stmt.where(ContentPlan.company_id == company_id)
    if platform is not None:
        stmt = stmt.where(ContentItem.platform == platform)

    rows = (await session.execute(stmt)).all()
    return ContentItemListResponse(
        items=[
            ContentItemWithCompanyOut(
                **ContentItemOut.model_validate(item).model_dump(),
                company_id=item_company_id,
                company_name=company_name,
            )
            for item, item_company_id, company_name in rows
        ]
    )


@router.patch("/content-items/{item_id}", response_model=ContentItemOut)
async def update_content_item(
    item_id: uuid.UUID,
    payload: ContentItemUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemOut:
    """Content preview & approval flow, drag-and-drop rescheduling, and
    hand-editing the draft copy in the Draft Workspace — all plain field
    updates on an existing item, no regeneration."""
    item, content_plan = await _get_item_and_plan_or_404(session, item_id, user)

    if payload.approval_status is not None:
        item.approval_status = payload.approval_status
        item.approved_by = payload.approved_by
    if payload.suggested_date is not None:
        item.suggested_date = payload.suggested_date
    if payload.draft_copy is not None and payload.draft_copy != item.draft_copy:
        # Snapshot the *previous* value before overwriting — nothing is
        # ever silently lost to a hand-edit.
        if item.draft_copy is not None:
            session.add(
                ContentItemRevision(
                    id=uuid.uuid4(),
                    content_item_id=item.id,
                    draft_copy=item.draft_copy,
                    edited_by=payload.edited_by,
                )
            )
        item.draft_copy = payload.draft_copy
    if payload.hashtags is not None:
        item.hashtags = payload.hashtags
    if payload.reviewer is not None:
        item.reviewer = payload.reviewer

    if payload.approval_status == "approved":
        # Index into the shared Knowledge Base on approval (not on every
        # generation/edit) — so plain KB search and the chat agent's
        # search_knowledge_base tool can find a company's own real
        # approved captions, not just externally-scraped material.
        if content_plan is not None:
            await index_on_approval(
                session,
                content_plan.company_id,
                "content_item",
                f"content-item://{item.id}",
                item.draft_copy or item.description,
            )

    await session.commit()
    await session.refresh(item)
    return ContentItemOut.model_validate(item)


@router.post("/content-items/{item_id}/schedule", response_model=ContentItemOut)
async def schedule_content_item(
    item_id: uuid.UUID,
    payload: ScheduleContentItemRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemOut:
    """Sets (or, with `scheduled_at: null`, clears) when the scheduled-
    publishing job should attempt to publish this item. Scheduling and
    approval are independent gates — the job only publishes an item that
    is BOTH scheduled and approved (see `run_scheduled_publishing`), so
    scheduling an unapproved draft is allowed here but won't publish
    until it's also approved."""
    item, _ = await _get_item_and_plan_or_404(session, item_id, user)
    if item.published_at is not None:
        raise HTTPException(status_code=409, detail="This item has already been published.")

    item.scheduled_at = payload.scheduled_at
    await session.commit()
    await session.refresh(item)
    return ContentItemOut.model_validate(item)


@router.post("/content-items/{item_id}/regenerate-draft", response_model=ContentItemOut)
async def regenerate_content_item_draft(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemOut:
    """Rewrite this item's draft copy — the calendar detail panel's
    "regenerate" action, for when the first draft isn't right. Runs a
    single Claude call synchronously, same latency profile as the other
    content-management POSTs."""
    # Checked here rather than inside `regenerate_item_draft_copy`, which
    # opens its own session and is also reachable from the chat agent's
    # confirmed-action path (already ownership-checked at its own entry).
    await _get_item_and_plan_or_404(session, item_id, user)
    item, ok = await regenerate_item_draft_copy(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Draft regeneration failed (check ANTHROPIC_API_KEY / Claude API availability).",
        )
    return ContentItemOut.model_validate(item)


@router.post("/content-items/{item_id}/repurpose", response_model=ContentItemOut)
async def repurpose_content_item_endpoint(
    item_id: uuid.UUID,
    payload: ContentItemRepurposeRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemOut:
    """Adapts an existing item's message into a NEW item for a different
    platform/format — the Content Repurposing Engine. Creates a fresh
    `ContentItem` in the source's company's manual plan (same reusable
    per-company plan `create_manual_content_item` writes into), leaving
    the source item untouched. `repurposed_from_id` traces the new item
    back to where it came from."""
    source, content_plan = await _get_item_and_plan_or_404(session, item_id, user)
    if not source.draft_copy:
        raise HTTPException(status_code=400, detail="This item has no draft copy to repurpose yet.")

    company = await _get_ready_company_or_error(session, content_plan.company_id, user)
    manual_plan = await _get_or_create_manual_plan(session, content_plan.company_id)

    kb_references = await fetch_kb_references(session, content_plan.company_id, source.title)
    context = format_context(company, None, [], kb_references)

    generated, ok = await repurpose_content_item(
        context, source.title, source.draft_copy, payload.platform, payload.content_type
    )
    if not ok or generated is None:
        raise HTTPException(
            status_code=502,
            detail="Content repurposing failed (check ANTHROPIC_API_KEY / Claude API availability).",
        )

    new_item = ContentItem(
        id=uuid.uuid4(),
        content_plan_id=manual_plan.id,
        title=generated.title,
        description=generated.description,
        content_type=generated.content_type,
        platform=generated.platform,
        suggested_date=generated.suggested_date,
        draft_copy=generated.draft_copy,
        hashtags=generated.hashtags,
        repurposed_from_id=source.id,
        approval_status="pending",
    )
    session.add(new_item)
    await session.commit()
    await session.refresh(new_item)
    return ContentItemOut.model_validate(new_item)


@router.post("/content-items/{item_id}/quality-check", response_model=ContentItemOut)
async def check_content_item_quality(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemOut:
    """Reviews the item's current draft_copy for grammar/tone/formatting
    issues and brand-voice consistency — one Claude call covering both,
    not two separate systems. Overwrites the previous check result
    (single current state, not versioned like draft_copy's revisions)."""
    item, content_plan = await _get_item_and_plan_or_404(session, item_id, user)
    if not item.draft_copy:
        raise HTTPException(status_code=400, detail="This item has no draft copy to check yet.")

    company = await session.get(Company, content_plan.company_id)

    result, ok = await check_content_quality(
        item.draft_copy, company.brand_voice if company else None, item.platform
    )
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Quality check failed (check ANTHROPIC_API_KEY / Claude API availability).",
        )

    item.quality_check_passed = result.passed
    notes_parts = [result.notes] if result.notes else []
    if result.issues:
        notes_parts.append("Issues: " + "; ".join(result.issues))
    item.quality_check_notes = " ".join(notes_parts) or None

    await session.commit()
    await session.refresh(item)
    return ContentItemOut.model_validate(item)


@router.post(
    "/content-items/{item_id}/creative-brief", response_model=ContentItemCreativeBriefOut
)
async def create_content_item_creative_brief(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemCreativeBriefOut:
    """Generates a production brief (hook, shot list, visual direction,
    editing notes) for one content item. Overwrites any existing brief for
    this item — single current state, not versioned like draft_copy's
    revisions."""
    item, content_plan = await _get_item_and_plan_or_404(session, item_id, user)

    company = await session.get(Company, content_plan.company_id)
    strategy = (
        await session.get(Strategy, content_plan.strategy_id)
        if content_plan.strategy_id
        else None
    )
    if company is None:
        raise HTTPException(status_code=404, detail="Company for this content item not found")

    context = format_context(company, strategy, [])
    generated, ok = await generate_creative_brief(
        context, item.title, item.description, item.platform, item.content_type
    )
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Creative brief generation failed (check ANTHROPIC_API_KEY / Claude API availability).",
        )

    brief = (
        await session.execute(
            select(ContentItemCreativeBrief).where(
                ContentItemCreativeBrief.content_item_id == item_id
            )
        )
    ).scalar_one_or_none()
    if brief is None:
        brief = ContentItemCreativeBrief(id=uuid.uuid4(), content_item_id=item_id)
        session.add(brief)

    brief.hook = generated.hook
    brief.shot_list = generated.shot_list
    brief.visual_references = generated.visual_references
    brief.editing_notes = generated.editing_notes
    brief.thumbnail_concept = generated.thumbnail_concept

    await session.commit()
    await session.refresh(brief)
    return ContentItemCreativeBriefOut.model_validate(brief)


@router.get(
    "/content-items/{item_id}/creative-brief", response_model=ContentItemCreativeBriefOut
)
async def get_content_item_creative_brief(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemCreativeBriefOut:
    await _get_item_and_plan_or_404(session, item_id, user)
    brief = (
        await session.execute(
            select(ContentItemCreativeBrief).where(
                ContentItemCreativeBrief.content_item_id == item_id
            )
        )
    ).scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=404, detail="No creative brief generated yet")
    return ContentItemCreativeBriefOut.model_validate(brief)


@router.get("/content-items/{item_id}/revisions", response_model=ContentItemRevisionListResponse)
async def list_content_item_revisions(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemRevisionListResponse:
    await _get_item_and_plan_or_404(session, item_id, user)
    rows = (
        (
            await session.execute(
                select(ContentItemRevision)
                .where(ContentItemRevision.content_item_id == item_id)
                .order_by(ContentItemRevision.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return ContentItemRevisionListResponse(
        items=[ContentItemRevisionOut.model_validate(row) for row in rows]
    )


@router.get("/content-items/{item_id}/comments", response_model=ContentItemCommentListResponse)
async def list_content_item_comments(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemCommentListResponse:
    await _get_item_and_plan_or_404(session, item_id, user)
    rows = (
        (
            await session.execute(
                select(ContentItemComment)
                .where(ContentItemComment.content_item_id == item_id)
                .order_by(ContentItemComment.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return ContentItemCommentListResponse(
        items=[ContentItemCommentOut.model_validate(row) for row in rows]
    )


@router.post("/content-items/{item_id}/comments", response_model=ContentItemCommentOut)
async def create_content_item_comment(
    item_id: uuid.UUID,
    payload: ContentItemCommentCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ContentItemCommentOut:
    await _get_item_and_plan_or_404(session, item_id, user)

    comment = ContentItemComment(
        id=uuid.uuid4(), content_item_id=item_id, author=payload.author, body=payload.body
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return ContentItemCommentOut.model_validate(comment)


@router.post("/campaigns", response_model=CampaignOut)
async def create_campaign(
    payload: CampaignCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CampaignOut:
    await _get_ready_company_or_error(session, payload.company_id, user)
    if payload.content_plan_id is not None:
        content_plan = await session.get(ContentPlan, payload.content_plan_id)
        if content_plan is None:
            raise HTTPException(status_code=404, detail="Content plan not found")
        if content_plan.company_id != payload.company_id:
            raise HTTPException(
                status_code=400, detail="Content plan does not belong to the given company"
            )
    if payload.strategy_id is not None:
        strategy = await session.get(Strategy, payload.strategy_id)
        if strategy is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        if strategy.company_id != payload.company_id:
            raise HTTPException(
                status_code=400, detail="Strategy does not belong to the given company"
            )

    campaign = Campaign(
        id=uuid.uuid4(),
        company_id=payload.company_id,
        content_plan_id=payload.content_plan_id,
        strategy_id=payload.strategy_id,
        status="pending",
    )
    session.add(campaign)
    await session.commit()

    await run_campaign_generation(
        campaign.id, payload.company_id, payload.content_plan_id, payload.strategy_id
    )

    # populate_existing=True — same identity-map staleness reason as
    # create_strategy above.
    refreshed = (
        await session.execute(
            select(Campaign)
            .execution_options(populate_existing=True)
            .where(Campaign.id == campaign.id)
        )
    ).scalar_one()
    return CampaignOut.model_validate(refreshed)


@router.get("/campaigns", response_model=CampaignListResponse)
async def list_campaigns(
    company_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CampaignListResponse:
    visible = accessible_company_id_clause(user, Campaign.company_id)
    stmt = select(Campaign).where(visible).order_by(Campaign.created_at.desc())
    count_stmt = select(func.count()).select_from(Campaign).where(visible)
    if company_id is not None:
        stmt = stmt.where(Campaign.company_id == company_id)
        count_stmt = count_stmt.where(Campaign.company_id == company_id)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return CampaignListResponse(items=[CampaignOut.model_validate(row) for row in rows], total=total)


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CampaignOut:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await ensure_company_access(session, campaign.company_id, user)
    return CampaignOut.model_validate(campaign)


@router.patch("/campaigns/{campaign_id}/lifecycle", response_model=CampaignOut)
async def update_campaign_lifecycle(
    campaign_id: uuid.UUID,
    payload: CampaignLifecycleUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CampaignOut:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await ensure_company_access(session, campaign.company_id, user)
    campaign.lifecycle_stage = payload.lifecycle_stage
    await session.commit()
    await session.refresh(campaign)
    return CampaignOut.model_validate(campaign)


@router.post("/collaborations", response_model=CollaborationOut)
async def create_collaboration(
    payload: CollaborationCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CollaborationOut:
    await _get_ready_company_or_error(session, payload.company_id, user)
    if payload.strategy_id is not None:
        strategy = await session.get(Strategy, payload.strategy_id)
        if strategy is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        if strategy.company_id != payload.company_id:
            raise HTTPException(
                status_code=400, detail="Strategy does not belong to the given company"
            )

    collaboration = Collaboration(
        id=uuid.uuid4(), company_id=payload.company_id, strategy_id=payload.strategy_id, status="pending"
    )
    session.add(collaboration)
    await session.commit()

    await run_collaboration_generation(collaboration.id, payload.company_id, payload.strategy_id)

    # populate_existing=True — same identity-map staleness reason as
    # create_content_plan above.
    refreshed = (
        await session.execute(
            select(Collaboration)
            .options(selectinload(Collaboration.ideas))
            .execution_options(populate_existing=True)
            .where(Collaboration.id == collaboration.id)
        )
    ).scalar_one()
    return CollaborationOut.model_validate(refreshed)


@router.get("/collaborations", response_model=CollaborationListResponse)
async def list_collaborations(
    company_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CollaborationListResponse:
    visible = accessible_company_id_clause(user, Collaboration.company_id)
    stmt = select(Collaboration).where(visible).order_by(Collaboration.created_at.desc())
    count_stmt = select(func.count()).select_from(Collaboration).where(visible)
    if company_id is not None:
        stmt = stmt.where(Collaboration.company_id == company_id)
        count_stmt = count_stmt.where(Collaboration.company_id == company_id)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return CollaborationListResponse(
        items=[CollaborationSummaryOut.model_validate(row) for row in rows], total=total
    )


@router.get("/collaborations/{collaboration_id}", response_model=CollaborationOut)
async def get_collaboration(
    collaboration_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CollaborationOut:
    collaboration = (
        await session.execute(
            select(Collaboration)
            .options(selectinload(Collaboration.ideas))
            .where(Collaboration.id == collaboration_id)
        )
    ).scalar_one_or_none()
    if collaboration is None:
        raise HTTPException(status_code=404, detail="Collaboration not found")
    await ensure_company_access(session, collaboration.company_id, user)
    return CollaborationOut.model_validate(collaboration)
