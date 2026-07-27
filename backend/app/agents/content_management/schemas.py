"""Internal data shapes for Content Management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class GeneratedStrategy:
    """Claude's structured output for `generate_strategy`."""

    summary: str | None = None
    marketing_strategy: str | None = None
    campaign_direction: str | None = None
    growth_recommendations: str | None = None
    business_suggestions: str | None = None


@dataclass(slots=True)
class GeneratedContentItem:
    """One calendar entry from `generate_content_plan`, before persistence
    (dates are already resolved from the model's relative `days_from_now`;
    `related_trend_title` is resolved to `source_trend_id` by the graph,
    not here — this dataclass doesn't know about DB ids)."""

    title: str
    description: str
    content_type: str
    platform: str
    suggested_date: date
    theme: str | None = None
    related_trend_title: str | None = None
    audience_interest: str | None = None
    seasonal_event: str | None = None
    # The actual finished, publishable copy — what someone pastes and
    # posts, not a brief of what it should say. See content_planner.py's
    # tool description for the prompt-level distinction from `description`.
    draft_copy: str | None = None


@dataclass(slots=True)
class GeneratedContentPlan:
    items: list[GeneratedContentItem] = field(default_factory=list)


@dataclass(slots=True)
class GeneratedCampaign:
    """Claude's structured output for `generate_campaign`. `start_date`/
    `end_date` are optional — Claude may leave the timeline unset when no
    content plan was given to seed it from."""

    name: str | None = None
    objective: str | None = None
    budget_allocation: str | None = None
    success_metrics: str | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass(slots=True)
class GeneratedCollaborationIdea:
    """One partnership idea from `generate_collaboration` — an archetype
    (e.g. "micro-influencer food bloggers"), not a named real account, since
    there's no live social search available to find actual candidates."""

    collaborator_archetype: str
    partnership_angle: str
    outreach_template: str
    priority: str
    rationale: str | None = None


@dataclass(slots=True)
class GeneratedCollaboration:
    ideas: list[GeneratedCollaborationIdea] = field(default_factory=list)
