"use client";

import { useRouter } from "next/navigation";
import { useState, type DragEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  createCampaign,
  updateContentItem,
  type ApprovalStatus,
  type ContentItem,
  type ContentPlan,
} from "@/lib/api";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const APPROVAL_BORDER_STYLES: Record<ApprovalStatus, string> = {
  pending: "border-border",
  approved: "border-primary",
  rejected: "border-destructive opacity-60",
};

const APPROVAL_BADGE_STYLES: Record<ApprovalStatus, string> = {
  pending: "",
  approved: "bg-primary/15 text-primary",
  rejected: "bg-destructive/10 text-destructive",
};

function formatDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function toIsoDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

// Weeks (Sun–Sat) spanning every item's suggested_date, padded to full
// weeks so the grid always renders complete rows.
function buildWeeks(items: ContentItem[]): Date[][] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const dates = items.map((item) => new Date(`${item.suggested_date}T00:00:00`));
  const min = dates.length > 0 ? new Date(Math.min(...dates.map((d) => d.getTime()))) : today;
  const max = dates.length > 0 ? new Date(Math.max(...dates.map((d) => d.getTime()))) : today;

  const start = new Date(min);
  start.setDate(start.getDate() - start.getDay());
  const end = new Date(max);
  end.setDate(end.getDate() + (6 - end.getDay()));

  const weeks: Date[][] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    const week: Date[] = [];
    for (let i = 0; i < 7; i++) {
      week.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  }
  return weeks;
}

export function ContentPlanView({
  contentPlan,
  trendTitlesById,
}: {
  contentPlan: ContentPlan;
  trendTitlesById: Record<string, string>;
}) {
  const router = useRouter();
  const [items, setItems] = useState(contentPlan.items);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dragOverDate, setDragOverDate] = useState<string | null>(null);
  const [itemError, setItemError] = useState<string | null>(null);
  const [generatingCampaign, setGeneratingCampaign] = useState(false);
  const [campaignError, setCampaignError] = useState<string | null>(null);

  const statusVariant = contentPlan.status === "complete" ? "default" : "outline";
  const weeks = buildWeeks(items);
  const itemsByDate = items.reduce<Record<string, ContentItem[]>>((acc, item) => {
    (acc[item.suggested_date] ??= []).push(item);
    return acc;
  }, {});
  const selectedItem = items.find((item) => item.id === selectedId) ?? null;

  async function persistItemUpdate(
    itemId: string,
    updates: { approvalStatus?: ApprovalStatus; suggestedDate?: string },
  ) {
    setItemError(null);
    try {
      const updated = await updateContentItem(itemId, updates);
      setItems((prev) => prev.map((item) => (item.id === itemId ? updated : item)));
    } catch (err) {
      setItemError(err instanceof Error ? err.message : "Failed to update content item.");
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>, targetDate: string) {
    e.preventDefault();
    setDragOverDate(null);
    const itemId = e.dataTransfer.getData("text/plain");
    if (!itemId) return;
    void persistItemUpdate(itemId, { suggestedDate: targetDate });
  }

  async function handleGenerateCampaign() {
    setGeneratingCampaign(true);
    setCampaignError(null);
    try {
      const campaign = await createCampaign(contentPlan.company_id, {
        contentPlanId: contentPlan.id,
        strategyId: contentPlan.strategy_id ?? undefined,
      });
      router.push(`/campaign/${campaign.id}`);
    } catch (err) {
      setCampaignError(err instanceof Error ? err.message : "Failed to generate campaign.");
      setGeneratingCampaign(false);
    }
  }

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Content calendar</h1>
        <Badge variant={statusVariant}>{contentPlan.status}</Badge>
      </div>

      {contentPlan.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Content plan generation failed
              {contentPlan.status_error ? `: ${contentPlan.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {contentPlan.status !== "failed" && items.length === 0 && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              {contentPlan.status === "complete"
                ? "No content items were generated."
                : "Generating content plan…"}
            </p>
          </CardContent>
        </Card>
      )}

      {items.length > 0 && (
        <Card>
          <CardContent className="pt-6">
            <div className="grid grid-cols-7 gap-2 text-xs font-medium text-muted-foreground">
              {WEEKDAY_LABELS.map((label) => (
                <div key={label} className="px-1">
                  {label}
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-col gap-2">
              {weeks.map((week) => (
                <div key={week[0].toISOString()} className="grid grid-cols-7 gap-2">
                  {week.map((day) => {
                    const iso = toIsoDate(day);
                    const dayItems = itemsByDate[iso] ?? [];
                    return (
                      <div
                        key={iso}
                        onDragOver={(e) => {
                          e.preventDefault();
                          setDragOverDate(iso);
                        }}
                        onDragLeave={() =>
                          setDragOverDate((prev) => (prev === iso ? null : prev))
                        }
                        onDrop={(e) => handleDrop(e, iso)}
                        className={`min-h-24 rounded-md border p-1.5 text-xs transition-colors ${
                          dragOverDate === iso ? "border-primary bg-muted" : "border-border"
                        }`}
                      >
                        <div className="mb-1 text-muted-foreground">{day.getDate()}</div>
                        <div className="flex flex-col gap-1">
                          {dayItems.map((item) => (
                            <button
                              key={item.id}
                              type="button"
                              draggable
                              onDragStart={(e) => e.dataTransfer.setData("text/plain", item.id)}
                              onClick={() => setSelectedId(item.id)}
                              title={item.title}
                              className={`w-full cursor-grab truncate rounded border bg-card px-1.5 py-1 text-left hover:bg-muted active:cursor-grabbing ${
                                APPROVAL_BORDER_STYLES[item.approval_status]
                              } ${selectedId === item.id ? "ring-1 ring-primary" : ""}`}
                            >
                              {item.title}
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Drag an item to a different day to reschedule it. Click an item to preview and
              approve or reject it.
            </p>
          </CardContent>
        </Card>
      )}

      {itemError && <p className="text-sm text-destructive">{itemError}</p>}

      {selectedItem && (
        <ContentItemDetail
          item={selectedItem}
          trendTitle={
            selectedItem.source_trend_id ? trendTitlesById[selectedItem.source_trend_id] : undefined
          }
          onApprove={() => persistItemUpdate(selectedItem.id, { approvalStatus: "approved" })}
          onReject={() => persistItemUpdate(selectedItem.id, { approvalStatus: "rejected" })}
          onClose={() => setSelectedId(null)}
        />
      )}

      {contentPlan.status === "complete" && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-3">
            <Button onClick={handleGenerateCampaign} disabled={generatingCampaign}>
              {generatingCampaign ? "Generating campaign…" : "Generate campaign"}
            </Button>
          </div>
          {campaignError && <p className="text-sm text-destructive">{campaignError}</p>}
        </div>
      )}
    </div>
  );
}

function ContentItemDetail({
  item,
  trendTitle,
  onApprove,
  onReject,
  onClose,
}: {
  item: ContentItem;
  trendTitle?: string;
  onApprove: () => void;
  onReject: () => void;
  onClose: () => void;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">{item.title}</h2>
            <span className="text-sm text-muted-foreground">{formatDate(item.suggested_date)}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>

        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{item.platform}</Badge>
          <Badge variant="outline">{item.content_type}</Badge>
          {item.theme && <Badge variant="default">{item.theme}</Badge>}
          {item.seasonal_event && <Badge variant="outline">{item.seasonal_event}</Badge>}
          <Badge className={APPROVAL_BADGE_STYLES[item.approval_status]} variant="default">
            {item.approval_status}
          </Badge>
        </div>

        <p className="text-sm leading-relaxed">{item.description}</p>

        {item.audience_interest && (
          <p className="text-xs text-muted-foreground">Audience: {item.audience_interest}</p>
        )}
        {trendTitle && (
          <p className="text-xs text-muted-foreground">Inspired by trend: {trendTitle}</p>
        )}

        <div className="flex flex-wrap gap-3">
          <Button
            variant={item.approval_status === "approved" ? "secondary" : "default"}
            size="sm"
            onClick={onApprove}
            disabled={item.approval_status === "approved"}
          >
            Approve
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onReject}
            disabled={item.approval_status === "rejected"}
          >
            Reject
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
