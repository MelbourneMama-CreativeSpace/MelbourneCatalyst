"use client";

import { ExternalLink } from "lucide-react";

import { PublishPanel } from "@/components/publish-panel";
import { PlatformIcon } from "@/components/social-icons";
import type { ChatCard, ContentItemCard, TrendCard } from "@/lib/api";

// Renders the small structured snapshots a chat reply carries — a content
// item just created/found, a trend surfaced — as flashcards, instead of
// leaving the assistant to only ever describe them in prose. Shown right
// under a reply's text, same message bubble.
export function ChatCards({ cards }: { cards: ChatCard[] }) {
  if (cards.length === 0) return null;
  return (
    <div className="mt-2 flex flex-col gap-2">
      {cards.map((card) =>
        card.type === "content_item" ? (
          <ContentItemFlashcard key={card.id} card={card} />
        ) : (
          <TrendFlashcard key={card.id} card={card} />
        ),
      )}
    </div>
  );
}

function statusMeta(card: ContentItemCard): { label: string; className: string } {
  if (card.published_at) {
    return { label: "Published", className: "border-primary/30 bg-primary/10 text-primary" };
  }
  if (card.scheduled_at) {
    return {
      label: "Scheduled",
      className: "border-accent/40 bg-accent/15 text-accent-foreground",
    };
  }
  if (card.approval_status === "approved") {
    return { label: "Approved", className: "border-primary/30 bg-primary/10 text-primary" };
  }
  if (card.approval_status === "rejected") {
    return {
      label: "Rejected",
      className: "border-destructive/30 bg-destructive/10 text-destructive",
    };
  }
  return { label: "Draft", className: "border-border text-muted-foreground" };
}

function ContentItemFlashcard({ card }: { card: ContentItemCard }) {
  const meta = statusMeta(card);
  return (
    <div className="w-full max-w-md rounded-xl border border-border bg-card p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <PlatformIcon platform={card.platform} className="h-4 w-4 shrink-0" />
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
          {card.title}
        </p>
        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${meta.className}`}
        >
          {meta.label}
        </span>
      </div>

      {card.media_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={card.media_url}
          alt="Attached media"
          className="mt-2 max-h-40 w-full rounded-lg object-cover"
        />
      )}

      {card.draft_copy && (
        // Full content, not clamped — this is often the only place the
        // actual copy is visible before it's posted, so cutting it off
        // with a fade/ellipsis just hides content the user needs to
        // review. Capped with a scrollable max-height rather than an
        // unbounded card only so one very long draft can't push the rest
        // of the conversation off-screen.
        <p className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
          {card.draft_copy}
        </p>
      )}

      {card.hashtags && card.hashtags.length > 0 && (
        <p className="mt-1.5 text-xs text-primary">
          {card.hashtags.map((h) => `#${h}`).join(" ")}
        </p>
      )}

      {/* Publish/schedule controls only belong on a card when posting is
          literally what's being proposed (card_context: "action") — a
          card that's just showing a newly-drafted or found item
          ("preview") shouldn't invite a one-click publish nobody asked
          for yet. */}
      {card.card_context === "action" && (
        <div className="mt-3 border-t border-border/60 pt-2.5">
          <PublishPanel item={card} />
        </div>
      )}
    </div>
  );
}

function TrendFlashcard({ card }: { card: TrendCard }) {
  return (
    <a
      href={card.url}
      target="_blank"
      rel="noreferrer"
      className="group flex w-full max-w-md flex-col rounded-xl border border-border bg-card p-3 shadow-sm transition-colors hover:border-primary/40"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm font-semibold text-foreground group-hover:text-primary">
          {card.title}
        </p>
        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground group-hover:text-primary" />
      </div>
      <p className="mt-1 text-xs capitalize text-muted-foreground">
        {card.source}
        {card.category ? ` · ${card.category}` : ""}
        {card.relevance_score !== null ? ` · ${Math.round(card.relevance_score * 100)}% relevant` : ""}
      </p>
      {card.insight && (
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{card.insight}</p>
      )}
    </a>
  );
}
