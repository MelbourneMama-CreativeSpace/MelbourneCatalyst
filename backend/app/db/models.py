"""SQLAlchemy ORM models: trends, companies, the shared documents store, and
Content Management (strategies + content plans)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

# JSONB on Postgres (Supabase), plain JSON on SQLite (used in tests).
_MetadataType = JSON().with_variant(JSONB(), "postgresql")
# Postgres ARRAY(String) for niche_keywords; JSON list on SQLite for tests.
_StringArrayType = JSON().with_variant(ARRAY(String()), "postgresql")

# Voyage voyage-3-lite embedding dimensionality.
EMBEDDING_DIM = 1024
# Vector column on Postgres via pgvector; JSON list on SQLite so the ORM
# still loads/saves it (semantic-search queries are Postgres-only anyway).
_EmbeddingType = JSON().with_variant(Vector(EMBEDDING_DIM), "postgresql")


class Trend(Base):
    __tablename__ = "trends"
    __table_args__ = (UniqueConstraint("source", "url", name="uq_trends_source_url"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    insight: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Filled in by the Trend Analyzer graph's score_relevance node against
    # the current company's niche_keywords. Null when no company is
    # onboarded, or when scoring failed.
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyTrendRelevance(Base):
    """Per-(company, trend) relevance score, computed once when a trend is
    first discovered — against every `complete` company's niche_keywords at
    that time, not just one. Fixes the single-tenant assumption baked into
    `Trend.relevance_score` (which only ever reflected whichever company
    happened to be "most recently updated" at scoring time): with more than
    one onboarded company, that single global score was frequently right
    for the wrong client. Additive alongside `Trend.relevance_score` rather
    than replacing it — only the Content Planner's trend context currently
    reads this table (see content_plan_graph.py); other generation agents
    still read the legacy global score, a known gap tracked in
    KNOWN_ISSUES.md."""

    __tablename__ = "company_trend_relevance"
    __table_args__ = (
        UniqueConstraint("company_id", "trend_id", name="uq_company_trend_relevance_company_trend"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trend_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trends.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    # Nullable: a company can onboard from a typed description or its
    # connected social accounts instead of a website. Postgres allows any
    # number of NULLs under a UNIQUE constraint, so uniqueness still holds
    # for the companies that do have a URL.
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True, unique=True)
    # The operator's own words about the business — the profile-extraction
    # input when there is no site to scrape. Distinct from `summary`, which
    # is Claude's *output*; this is raw human input and is never overwritten
    # by extraction, so a re-onboard can always be replayed from it.
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Supabase user id of whoever onboarded this company. Nullable only for
    # rows created before ownership existed — see app/security/ownership.py
    # for how those are treated (inaccessible, not shared).
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # `name` is nullable because the extractor fills it in during
    # onboarding — it doesn't exist yet when the pending row is created.
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Onboarding lifecycle: pending -> scraping -> extracting ->
    # complete | complete_no_profile | failed. complete_no_profile means
    # scraping succeeded but no profile could be extracted (e.g. missing
    # ANTHROPIC_API_KEY) — distinct from a silent "complete" with blank fields.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    # All extracted profile fields are nullable so the row can exist in a
    # pending state before Claude has filled it in.
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String, nullable=True)
    brand_voice: Mapped[str | None] = mapped_column(String, nullable=True)
    unique_value_prop: Mapped[str | None] = mapped_column(String, nullable=True)
    niche_keywords: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    products_and_services: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)

    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list[Document]] = relationship(back_populates="company", cascade="all, delete-orphan")


class CompanyMember(Base):
    """Who is allowed to act on a given company — the per-company half of
    authorization that `get_current_user` (which only proves *someone* is
    signed in) deliberately left open.

    Membership rather than a single `companies.owner_id` because this app
    already assumes several people work one client: `approved_by`,
    `reviewer`, and the /approvals "Assign to me" toggle all exist. A single
    owner column would have needed replacing the first time a second person
    touched an account.

    `user_id` is a plain string, not a foreign key: it holds the Supabase
    `sub` claim, and Supabase's `auth.users` lives in a schema this app has
    no business referencing (and which doesn't exist at all under SQLite in
    tests). Same reasoning as `approved_by`/`reviewer` storing free text.

    Exactly one of `user_id` / `invited_email` is set:

    - `user_id` — a real, resolved member. This is what access checks match.
    - `invited_email` — someone invited before they ever signed in. Carries
      no access on its own; `ensure_company_access` binds it to a real
      `user_id` the first time a user whose token carries that email address
      accesses the company. This avoids needing Supabase's Admin API (and a
      service-role key) just to turn an email into a user id.
    """

    __tablename__ = "company_members"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_members_company_user"),
        UniqueConstraint("company_id", "invited_email", name="uq_company_members_company_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    invited_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Recorded for display ("who's on this account") — access checks use
    # user_id only, since an email claim can change without the id changing.
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # 'owner' (created or first claimed the company) | 'member' (invited).
    # Both have identical access today — the distinction exists so a future
    # round can restrict destructive actions without another migration.
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # e.g. "website", "blog", "product_page" — future: "social_post", "doc_upload".
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    embedding = mapped_column(_EmbeddingType, nullable=True)
    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="documents")


class MediaAsset(Base):
    """One uploaded file in the Media & Asset Library, stored in Supabase
    Storage — this row is the searchable/filterable record; the actual
    bytes live in the bucket, referenced by `storage_path`. Search this
    round is tag/filename-based, not embedding-based (per the standing
    scoping note: keyword search alone is real day-one value; visual
    similarity search is a later stretch goal, not attempted here)."""

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    # The object key inside the configured Supabase Storage bucket —
    # this app's reference to the actual file, same "we only hold the
    # reference" pattern as Composio's connected-account ids.
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Only set if the bucket is public; null means the file exists but
    # has no directly-browsable URL (a private bucket would need signed
    # URLs generated on demand, not attempted this round).
    public_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # One-shot generation lifecycle: pending -> complete | failed. Simpler
    # than Company's status set — a single Claude call, no partial-success
    # "scraped but no profile" state to represent here.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    marketing_strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    campaign_direction: Mapped[str | None] = mapped_column(String, nullable=True)
    growth_recommendations: Mapped[str | None] = mapped_column(String, nullable=True)
    business_suggestions: Mapped[str | None] = mapped_column(String, nullable=True)

    # Manual review lifecycle, independent of `status` above (which is
    # only the generation lifecycle) — same pattern as
    # ContentItem.approval_status.
    approval_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
    # Free-text name of whoever last changed `approval_status` — same
    # lightweight attribution as ContentItem.approved_by, not a real auth
    # system. Null until the first approval/rejection.
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Free-text name of whoever is assigned to review this — same
    # lightweight attribution pattern as approved_by, not a real per-user
    # identity. Independent of approval_status: assigning a reviewer
    # doesn't itself approve/reject anything.
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentPlan(Base):
    __tablename__ = "content_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optional — a plan can be generated straight from the company profile
    # + trends without an explicit prior strategy.
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)
    # True for the one reusable per-company plan that holds manually
    # input items (see content_management.py's `_get_or_create_manual_plan`)
    # — distinguishes it from AI-generated calendars so the two never mix
    # in a company's plan history.
    is_manual: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list[ContentItem]] = relationship(
        back_populates="content_plan", cascade="all, delete-orphan", order_by="ContentItem.suggested_date"
    )


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    content_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    theme: Mapped[str | None] = mapped_column(String(256), nullable=True)
    suggested_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Best-effort match back to the Trend that inspired this idea (matched
    # by title against the trends passed as generation context) — nullable
    # since not every idea traces to a specific trend, and SET NULL so an
    # old trend disappearing doesn't take the content idea down with it.
    source_trend_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trends.id", ondelete="SET NULL"), nullable=True
    )
    # Which audience segment/interest (drawn from the company's profile)
    # this idea is aimed at — Claude-generated, distinct from `theme` which
    # is a content/campaign tag rather than an audience descriptor.
    audience_interest: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Name of the seasonal/awareness event (e.g. "Mother's Day") this idea
    # ties to, if Claude chose to tie it to one of the candidates offered in
    # generation context for the plan's date window. Null for evergreen ideas.
    seasonal_event: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # The actual finished, publishable copy for this item — what someone
    # pastes and posts. Distinct from `description`, which is a brief of
    # what the content says/shows, not the content itself. Nullable: older
    # rows generated before this field existed, and the graceful
    # no-`ANTHROPIC_API_KEY` failure path, both leave it unset.
    draft_copy: Mapped[str | None] = mapped_column(String, nullable=True)
    # Structured hashtags, without '#' — separate from any hashtags already
    # written inline into draft_copy's prose. Null for platforms/formats
    # that don't use them, or items generated before this field existed.
    hashtags: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)
    # A user-attached image (or video) for this item — a public Supabase
    # Storage URL, same shape as chat attachments. Nothing in this app
    # generates one; it's supplied by hand via POST .../media. Most
    # platforms don't need this (a caption alone is a valid post), but
    # Instagram's real API has no text-only post at all — every Instagram
    # publish requires this to be set, checked in publish.py, not here.
    media_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set when this item was created by the Content Repurposing Engine
    # (adapting another item's message for a different platform/format) —
    # a self-referential reference back to that source item, same shape
    # as source_trend_id below. SET NULL so deleting the source item
    # doesn't take a repurposed descendant down with it.
    repurposed_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True
    )
    # Manual review lifecycle, independent of ContentPlan.status (which is
    # only the generation lifecycle) — same "manually advanced, no
    # state-machine enforcement" pattern as Campaign.lifecycle_stage.
    approval_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
    # Free-text name of whoever last changed `approval_status` — not a real
    # auth system, just enough attribution for a small internal team to see
    # who signed off on what. Null until the first approval/rejection.
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Free-text name of whoever is assigned to review this — same
    # lightweight attribution pattern as approved_by, not a real per-user
    # identity. Independent of approval_status.
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # When set, the scheduled-publishing job (run_scheduled_publishing)
    # attempts to publish this item once `scheduled_at <= now()` and
    # `published_at IS NULL`. Null means "not scheduled" — publishing is
    # opt-in per item, not automatic once approved.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once a publish attempt actually succeeds — distinct from
    # scheduled_at so a still-pending scheduled item is never confused
    # with one that already went out.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Quality/brand-consistency check result — single current state,
    # overwritten by each new check, not versioned like draft_copy's
    # revisions. Null until the first check has run.
    quality_check_passed: Mapped[bool | None] = mapped_column(nullable=True)
    quality_check_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    content_plan: Mapped[ContentPlan] = relationship(back_populates="items")


class ContentItemRevision(Base):
    """A snapshot of `ContentItem.draft_copy` taken *before* each change —
    manual edits in the Draft Workspace and Claude regenerations both write
    one, so a prior draft is never silently lost. Not a full undo/redo
    system, just an append-only history."""

    __tablename__ = "content_item_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    draft_copy: Mapped[str] = mapped_column(String, nullable=False)
    # Free-text, same lightweight attribution pattern as ContentItem.approved_by.
    edited_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentItemComment(Base):
    __tablename__ = "content_item_comments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    body: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentItemCreativeBrief(Base):
    """A production brief (hook, shot list, visual direction, editing
    notes) for one ContentItem — one row per item, overwritten on
    regeneration rather than versioned like ContentItemRevision, same
    single-current-state shape as the quality check fields."""

    __tablename__ = "content_item_creative_briefs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    hook: Mapped[str | None] = mapped_column(String, nullable=True)
    shot_list: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)
    visual_references: Mapped[str | None] = mapped_column(String, nullable=True)
    editing_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_concept: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PublishAttempt(Base):
    """A log entry for one attempt to publish a ContentItem to one
    connected platform — same "record of what happened, don't overwrite
    it" shape as PlatformMetricSnapshot. Multiple rows can exist per
    ContentItem (e.g. a retry after a failure)."""

    __tablename__ = "publish_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform_connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "success" | "failed"
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)
    # Composio's execution id, when the attempt succeeded — a reference
    # for looking the post up on Composio's side later, not this app's PK.
    composio_execution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PostMetricSnapshot(Base):
    """Real per-post engagement metrics (likes/comments/shares/saves/
    views/reach), one row per fetch — same "log entry, never overwrite"
    shape as PublishAttempt/PlatformMetricSnapshot, so a metric's history
    over time is never lost, not just its latest value. Distinct from
    PlatformMetricSnapshot, which is account-level (follower count,
    overall engagement rate) — this is specifically per-ContentItem, the
    granularity LoomVerse's Analysis needs to answer "what worked" at the
    individual-post level, not just in aggregate.

    Every field is nullable on purpose: what's actually fetchable differs
    genuinely per platform (confirmed live against each real Composio
    toolkit, not assumed) — e.g. LinkedIn currently only exposes a
    reaction count, nothing for comments/shares/views/reach. A null here
    means "this platform doesn't expose this metric," never a fabricated
    zero."""

    __tablename__ = "post_metric_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saves: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reach: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Full raw response, for anything not yet promoted to its own column
    # (e.g. Reels-specific retention metrics) and for diagnosing a
    # surprising number against what the platform actually returned.
    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)


class AnalysisInsightCache(Base):
    """The Analysis page's AI "why" + "what's next" (see
    social_media_analyzer/analysis.py's generate_insight), memoized per
    (company, period_days) instead of regenerated on every page view.

    Before this existed, GET /analysis/overview called Claude fresh on
    every single request — a real, avoidable cost, since the underlying
    numbers only actually change on the post-metrics sync cadence
    (POST_METRICS_SYNC_INTERVAL_MINUTES), not on every page refresh.
    get_or_generate_insight treats a row here as fresh until it's older
    than that same interval, then regenerates and overwrites in place —
    one row per (company, period), not an append-only log like
    PostMetricSnapshot, since only the current insight is ever useful."""

    __tablename__ = "analysis_insight_cache"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_why: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_recommendations: Mapped[list[str]] = mapped_column(_StringArrayType, nullable=False, default=list)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_days", name="uq_analysis_insight_cache_company_period"
        ),
    )


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optional — a campaign can be generated straight from the company
    # profile + trends, or seeded from a prior content plan and/or strategy.
    content_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # One-shot generation lifecycle: pending -> complete | failed — same
    # meaning as Strategy.status.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    # Separate from `status` above: a manually-advanced lifecycle the user
    # drives after generation completes. No state-machine enforcement — any
    # of the five values is accepted via the lifecycle PATCH endpoint.
    lifecycle_stage: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)

    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    objective: Mapped[str | None] = mapped_column(String, nullable=True)
    budget_allocation: Mapped[str | None] = mapped_column(String, nullable=True)
    success_metrics: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Collaboration(Base):
    __tablename__ = "collaborations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ideas: Mapped[list[CollaborationIdea]] = relationship(
        back_populates="collaboration", cascade="all, delete-orphan"
    )


class CollaborationIdea(Base):
    __tablename__ = "collaboration_ideas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    collaboration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collaborations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # A collaborator profile ("micro-influencer food bloggers, 5-20k
    # followers, Melbourne-based") rather than a named real account — there's
    # no live social search available to find actual candidates.
    collaborator_archetype: Mapped[str] = mapped_column(String(256), nullable=False)
    partnership_angle: Mapped[str] = mapped_column(String, nullable=False)
    outreach_template: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collaboration: Mapped[Collaboration] = relationship(back_populates="ideas")


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # `name` is nullable because the extractor fills it in during onboarding
    # — same rationale as `Company.name`.
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Onboarding lifecycle — identical value set to Company.status. This is
    # the competitor's *own* scrape+extract pipeline, independent of the
    # comparison generation tracked by comparison_status below.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String, nullable=True)
    brand_voice: Mapped[str | None] = mapped_column(String, nullable=True)
    unique_value_prop: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)

    # Separate lifecycle from `status` above: whether the Company-vs-Competitor
    # comparison has been generated yet. pending -> complete | failed, same
    # meaning as Strategy.status; starts at not_started since comparison
    # can't run until both profiles exist.
    comparison_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="not_started", index=True
    )
    comparison_status_error: Mapped[str | None] = mapped_column(String, nullable=True)
    product_pricing_comparison: Mapped[str | None] = mapped_column(String, nullable=True)
    marketing_strategy_analysis: Mapped[str | None] = mapped_column(String, nullable=True)
    competitive_gaps: Mapped[str | None] = mapped_column(String, nullable=True)
    strategic_recommendations: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlatformConnection(Base):
    __tablename__ = "platform_connections"
    __table_args__ = (
        UniqueConstraint("company_id", "platform", name="uq_platform_connections_company_platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # instagram | facebook | twitter | linkedin | tiktok | youtube
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="disconnected", index=True
    )
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    # Composio custodies the actual OAuth tokens — this app never sees or
    # stores them, encrypted or otherwise. This is the id of the
    # corresponding Composio "connected account" (its `nanoid`), used to
    # check status and to disconnect.
    composio_connected_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    external_account_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_account_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    scopes: Mapped[str | None] = mapped_column(String, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class YouTubeUploadJob(Base):
    """A queued real YouTube video upload — retried by
    `run_scheduled_youtube_uploads` until it succeeds or hits
    `MAX_YOUTUBE_UPLOAD_ATTEMPTS`, rather than the one-shot synchronous
    attempt `upload_youtube_video_tool` used to make alone. Same
    "log what happened, keep the row" shape as `PublishAttempt`, but this
    one *is* the retryable unit of work (one row per upload, mutated in
    place across attempts) rather than an attempt log — a video upload
    isn't associated with a `ContentItem` the way a text post is, so
    there's no existing row to log attempts against."""

    __tablename__ = "youtube_upload_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    platform_connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)
    # unlisted | public | private — YouTube's own three privacyStatus
    # values. Defaults to unlisted (safest default: never searchable/public
    # unless the user explicitly asks), but is a real, user-settable choice
    # per upload, not a hardcoded constant.
    privacy_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unlisted")
    # pending | success | failed (failed = gave up after MAX_YOUTUBE_UPLOAD_ATTEMPTS)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)
    composio_execution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformMetricSnapshot(Base):
    """Storage shape for a future Performance Tracking sync writer — no
    writer exists yet (this round scaffolds schema + connection UI only,
    per the explicit scope decision), so this table is created but stays
    empty until a later round adds the per-platform metrics fetcher."""

    __tablename__ = "platform_metric_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    platform_connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    follower_count: Mapped[int | None] = mapped_column(nullable=True)
    engagement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrendReport(Base):
    __tablename__ = "trend_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)
    period_days: Mapped[int] = mapped_column(nullable=False)

    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    # Same JSON/ARRAY-variant pattern as Company.niche_keywords — a short
    # list of strings, not free text.
    key_themes: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)
    notable_trends_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    content_opportunities: Mapped[str | None] = mapped_column(String, nullable=True)
    campaign_alignment_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    competitor_relevance_notes: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatConversation(Base):
    """A conversation with the intelligent chat agent. Nullable
    `company_id` — a conversation can be scoped to one company (tool calls
    default to it) or general.

    `user_id` (the Supabase `sub`, same as `CompanyMember.user_id`) is what
    makes a conversation private. Unlike every other table here, a
    conversation isn't owned via its company — a general conversation has
    no company at all — so it carries the owning user directly. Null on
    rows created before ownership existed; those are claimed by the first
    user to open them, matching `ensure_company_access`'s behaviour for
    unclaimed companies."""

    __tablename__ = "chat_conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Nullable only for conversations created before per-user ownership
    # existed — see app/security/ownership.py for how those are treated.
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Set from the first user message once the agent has replied; null
    # until then (matches the sidebar's "New conversation" fallback label).
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    """Only final user/assistant text is persisted here — not raw Anthropic
    tool_use/tool_result content blocks. Each turn is reconstructed from
    this stored text history rather than replayed via Claude's own
    content-block format, same simplification every other agent in this
    codebase makes (they persist generated output, not the full Claude
    conversation transcript)."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(String, nullable=False)
    # Display-only record of which tools produced an assistant reply (e.g.
    # ["list_trending_topics"]) — not replayed back to Claude on the next
    # turn, just shown in the UI for transparency. Null for user messages.
    tool_calls_summary: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)
    # Set when the assistant wants to take a write action (approve/reject/
    # regenerate/create) — {"tool_name": ..., "tool_input": {...},
    # "description": "..."}. The chat loop never executes a write tool
    # itself; it stops and surfaces this instead, and only the
    # confirm-action endpoint actually runs it. Null on every message that
    # isn't a pending-or-resolved action proposal.
    proposed_action: Mapped[dict | None] = mapped_column(_MetadataType, nullable=True)
    action_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "pending" | "confirmed" | "cancelled"
    # Small structured snapshots — a content item just created/found, a
    # trend surfaced — the frontend renders as flashcards inline in the
    # chat instead of the assistant only ever describing things in prose.
    # Never replayed back to Claude, same display-only contract
    # `tool_calls_summary` already has. Null when a reply has none.
    cards: Mapped[list[dict] | None] = mapped_column(_MetadataType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[ChatConversation] = relationship(back_populates="messages")


class KnowledgeAuditReport(Base):
    __tablename__ = "knowledge_audit_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    coverage_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    identified_gaps: Mapped[str | None] = mapped_column(String, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(String, nullable=True)
    # How many Document rows existed for this company when the audit ran —
    # context for interpreting the report later, since the KB keeps growing.
    document_count_at_generation: Mapped[int] = mapped_column(nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
