"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ImagePlus, Send, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { describeError } from "@/lib/api-error";
import {
  listConnections,
  publishNow,
  removeContentItemMedia,
  scheduleContentItem,
  uploadContentItemMedia,
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
  "id" | "company_id" | "platform" | "scheduled_at" | "published_at" | "media_url"
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
  // Mirrors `item.published_at` locally so a successful publish collapses
  // this panel into the "Published" view immediately — `item` itself is
  // an immutable prop (a chat flashcard's snapshot from when the tool
  // call ran, or Content Studio's own list state), neither of which
  // re-fetches on its own just because *this* panel's own publish call
  // succeeded. Without this the card kept showing live "Publish now" /
  // "Attach image" / "Schedule" controls for an item that had, in fact,
  // already gone out.
  const [publishedAt, setPublishedAt] = useState(item.published_at);

  // Instagram's real API has no text-only post at all — every publish
  // there needs an actual image/video attached first (checked
  // server-side too; this is just so the user finds out before clicking
  // Publish, not after). Every other platform treats this as optional.
  const [mediaUrl, setMediaUrl] = useState(item.media_url);
  const [mediaUploading, setMediaUploading] = useState(false);
  const [mediaError, setMediaError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const needsMedia = item.platform === "instagram";

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
      if (res.status === "success") setPublishedAt(new Date().toISOString());
    } finally {
      setPublishing(false);
    }
  }

  async function handleMediaSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setMediaError(null);
    setMediaUploading(true);
    try {
      const updated = await uploadContentItemMedia(item.id, file);
      setMediaUrl(updated.media_url);
    } catch (err) {
      setMediaError(describeError(err));
    } finally {
      setMediaUploading(false);
    }
  }

  async function handleRemoveMedia() {
    setMediaError(null);
    setMediaUploading(true);
    try {
      const updated = await removeContentItemMedia(item.id);
      setMediaUrl(updated.media_url);
    } catch (err) {
      setMediaError(describeError(err));
    } finally {
      setMediaUploading(false);
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

  if (publishedAt) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
        Published {new Date(publishedAt).toLocaleString()}
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
              {needsMedia && (
                <div className="flex flex-col gap-1.5 border-b border-border/60 pb-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*,video/*"
                    onChange={handleMediaSelected}
                    disabled={mediaUploading}
                    className="hidden"
                  />
                  {mediaUrl ? (
                    <div className="flex items-center gap-2">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={mediaUrl}
                        alt="Attached media"
                        className="h-10 w-10 rounded object-cover"
                      />
                      <span className="flex-1 text-muted-foreground">Image attached</span>
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={handleRemoveMedia}
                        disabled={mediaUploading}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={mediaUploading}
                    >
                      <ImagePlus className="h-3.5 w-3.5" />
                      {mediaUploading ? "Uploading…" : "Attach image"}
                    </Button>
                  )}
                  {!mediaUrl && (
                    <p className="flex items-center gap-1.5 text-muted-foreground">
                      <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
                      Instagram needs an image or video attached before this can publish.
                    </p>
                  )}
                  {mediaError && <p className="text-destructive">{mediaError}</p>}
                </div>
              )}

              <div className="flex items-center gap-2">
                <Button
                  size="xs"
                  onClick={handlePublishNow}
                  disabled={publishing || (needsMedia && !mediaUrl)}
                >
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
                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                  {result.post_url ? (
                    <a
                      href={result.post_url}
                      target="_blank"
                      rel="noreferrer"
                      className="truncate underline hover:no-underline"
                    >
                      Published — view it live
                    </a>
                  ) : (
                    "Published."
                  )}
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
