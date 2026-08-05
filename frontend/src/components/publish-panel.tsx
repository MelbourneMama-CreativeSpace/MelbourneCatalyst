"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  listConnections,
  publishNow,
  scheduleContentItem,
  type ContentItemWithCompany,
  type PlatformConnection,
  type PublishResult,
} from "@/lib/api";

// Only these fields are actually used below — a structural (not nominal)
// type, so a chat flashcard's much smaller ContentItemCard shape works
// here unchanged, without needing every field a full ContentItemWithCompany
// carries.
type PublishableItem = Pick<
  ContentItemWithCompany,
  "id" | "company_id" | "platform" | "scheduled_at" | "published_at"
>;

// The one common publish/schedule surface every content item uses,
// regardless of platform — connection status, "publish now," and
// "schedule for later" are the same three controls no matter which
// social handle the item belongs to.
export function PublishPanel({ item }: { item: PublishableItem }) {
  const [open, setOpen] = useState(false);
  const [connections, setConnections] = useState<PlatformConnection[] | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [result, setResult] = useState<PublishResult | null>(null);
  const [scheduleValue, setScheduleValue] = useState("");
  const [scheduling, setScheduling] = useState(false);
  const [scheduledAt, setScheduledAt] = useState(item.scheduled_at);

  useEffect(() => {
    if (!open || connections !== null) return;
    listConnections(item.company_id).then((res) => setConnections(res.items));
  }, [open, connections, item.company_id]);

  const connection = connections?.find((c) => c.platform === item.platform) ?? null;
  const isConnected = connection?.status === "connected" && connection.id;

  async function handlePublishNow() {
    if (!connection?.id) return;
    setPublishing(true);
    setResult(null);
    try {
      const res = await publishNow(connection.id, item.id);
      setResult(res);
    } finally {
      setPublishing(false);
    }
  }

  async function handleSchedule() {
    if (!scheduleValue) return;
    setScheduling(true);
    try {
      const iso = new Date(scheduleValue).toISOString();
      await scheduleContentItem(item.id, iso);
      setScheduledAt(iso);
    } finally {
      setScheduling(false);
    }
  }

  async function handleClearSchedule() {
    setScheduling(true);
    try {
      await scheduleContentItem(item.id, null);
      setScheduledAt(null);
    } finally {
      setScheduling(false);
    }
  }

  if (item.published_at) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
        Published {new Date(item.published_at).toLocaleString()}
      </p>
    );
  }

  return (
    <div>
      <Button size="sm" variant="outline" onClick={() => setOpen((o) => !o)}>
        <Send className="h-3.5 w-3.5" />
        Publish
      </Button>

      {open && (
        <div className="mt-2 flex flex-col gap-2 rounded-md border border-border p-3 text-xs">
          {connections === null ? (
            <p className="text-muted-foreground">Checking connection…</p>
          ) : !isConnected ? (
            <p className="flex items-center gap-1.5 text-muted-foreground">
              <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
              {item.platform} isn&apos;t connected for this company yet — connect it from the
              company&apos;s Integrations page first.
            </p>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Button size="xs" onClick={handlePublishNow} disabled={publishing}>
                  {publishing ? "Publishing…" : "Publish now"}
                </Button>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="datetime-local"
                  value={scheduleValue}
                  onChange={(e) => setScheduleValue(e.target.value)}
                  className="rounded-md border border-input bg-transparent px-2 py-1 text-xs outline-none"
                />
                <Button
                  size="xs"
                  variant="outline"
                  onClick={handleSchedule}
                  disabled={!scheduleValue || scheduling}
                >
                  Schedule
                </Button>
                {scheduledAt && (
                  <Button size="xs" variant="ghost" onClick={handleClearSchedule} disabled={scheduling}>
                    Clear
                  </Button>
                )}
              </div>
              {scheduledAt && (
                <p className="text-muted-foreground">
                  Scheduled for {new Date(scheduledAt).toLocaleString()}
                </p>
              )}
            </>
          )}

          {result && (
            <p
              className={`flex items-center gap-1.5 ${
                result.status === "success" ? "text-primary" : "text-destructive"
              }`}
            >
              {result.status === "success" ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5" /> Published.
                </>
              ) : (
                <>
                  <AlertTriangle className="h-3.5 w-3.5" /> {result.status_error}
                </>
              )}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
