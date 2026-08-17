"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type DragEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { describeError } from "@/lib/api-error";
import {
  createCampaign,
  regenerateContentItemDraft,
  updateContentItem,
  type ApprovalStatus,
  type ContentItem,
  type ContentPlan,
} from "@/lib/api";

const APPROVER_NAME_STORAGE_KEY = "mmcs_approver_name";

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
  const [approverName, setApproverName] = useState("");
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  // Not a real auth system — just enough attribution for a small internal
  // team to see who approved what, remembered across visits so nobody has
  // to retype it for every item.
  useEffect(() => {
    // One-time read of a browser-only API on mount, not a live
    // subscription — localStorage has no change-event to subscribe to
    // here, and the value only otherwise changes via the input below.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setApproverName(localStorage.getItem(APPROVER_NAME_STORAGE_KEY) ?? "");
  }, []);

  function handleApproverNameChange(value: string) {
    setApproverName(value);
    localStorage.setItem(APPROVER_NAME_STORAGE_KEY, value);
  }

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
      const updated = await updateContentItem(itemId, {
        ...updates,
        approvedBy: updates.approvalStatus ? approverName || undefined : undefined,
      });
      setItems((prev) => prev.map((item) => (item.id === itemId ? updated : item)));
    } catch (err) {
      setItemError(describeError(err));
    }
  }

  async function handleRegenerateDraft(itemId: string) {
    setItemError(null);
    setRegeneratingId(itemId);
    try {
      const updated = await regenerateContentItemDraft(itemId);
      setItems((prev) => prev.map((item) => (item.id === itemId ? updated : item)));
    } catch (err) {
      setItemError(describeError(err));
    } finally {
      setRegeneratingId(null);
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
      setCampaignError(describeError(err));
      setGeneratingCampaign(false);
    }
  }

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Content calendar</h1>
        <Badge variant={statusVariant}>{contentPlan.status}</Badge>
      </div>

      <label className="flex max-w-xs flex-col gap-1 text-xs text-muted-foreground">
        Your name (recorded when you approve or reject an item)
        <input
          type="text"
          value={approverName}
          onChange={(e) => handleApproverNameChange(e.target.value)}
          placeholder="e.g. Priya"
          className="rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />
      </label>

      {contentPlan.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Caption drafting failed
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
                : "Drafting captions for this window…"}
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
              Drag an item to a different day to reschedule it. Click an item to review its
              drafted caption, copy it, or approve/reject it.
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
          regenerating={regeneratingId === selectedItem.id}
          onApprove={() => persistItemUpdate(selectedItem.id, { approvalStatus: "approved" })}
          onReject={() => persistItemUpdate(selectedItem.id, { approvalStatus: "rejected" })}
          onRegenerate={() => handleRegenerateDraft(selectedItem.id)}
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
  regenerating,
  onApprove,
  onReject,
  onRegenerate,
  onClose,
}: {
  item: ContentItem;
  trendTitle?: string;
  regenerating: boolean;
  onApprove: () => void;
  onReject: () => void;
  onRegenerate: () => void;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (!item.draft_copy) return;
    await navigator.clipboard.writeText(item.draft_copy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

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

        <div className="rounded-md border border-border bg-muted/40 p-3">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">
              Ready-to-publish draft
            </span>
            {item.draft_copy && (
              <div className="flex gap-1">
                <Button variant="ghost" size="sm" onClick={handleCopy}>
                  {copied ? "Copied" : "Copy"}
                </Button>
                <Button variant="ghost" size="sm" onClick={onRegenerate} disabled={regenerating}>
                  {regenerating ? "Regenerating…" : "Regenerate"}
                </Button>
              </div>
            )}
          </div>
          {item.draft_copy ? (
            <p className="text-sm leading-relaxed whitespace-pre-line">{item.draft_copy}</p>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                No draft yet — this item was planned before draft copy generation shipped.
              </p>
              <Button variant="outline" size="sm" onClick={onRegenerate} disabled={regenerating}>
                {regenerating ? "Generating…" : "Generate draft"}
              </Button>
            </div>
          )}
        </div>

        <p className="text-xs text-muted-foreground">Brief: {item.description}</p>

        {item.audience_interest && (
          <p className="text-xs text-muted-foreground">Audience: {item.audience_interest}</p>
        )}
        {trendTitle && (
          <p className="text-xs text-muted-foreground">Inspired by trend: {trendTitle}</p>
        )}
        {item.approved_by && (
          <p className="text-xs text-muted-foreground">
            {item.approval_status === "rejected" ? "Rejected" : "Approved"} by {item.approved_by}
          </p>
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
