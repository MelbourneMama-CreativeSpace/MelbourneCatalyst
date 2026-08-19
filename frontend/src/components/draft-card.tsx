"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clapperboard,
  MessageSquare,
  History,
  Repeat2,
  ShieldCheck,
  X as XIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { PublishPanel } from "@/components/publish-panel";
import {
  checkContentItemQuality,
  createContentItemComment,
  generateContentItemCreativeBrief,
  getContentItemCreativeBrief,
  listContentItemComments,
  listContentItemRevisions,
  repurposeContentItem,
  updateContentItem,
  type ContentItem,
  type ContentItemComment,
  type ContentItemCreativeBrief,
  type ContentItemRevision,
  type ContentItemWithCompany,
  type ContentType,
  type Platform,
} from "@/lib/api";

const REPURPOSE_PLATFORMS: Platform[] = [
  "instagram",
  "linkedin",
  "twitter",
  "tiktok",
  "youtube",
  "blog",
  "facebook",
  "threads",
];
const REPURPOSE_CONTENT_TYPES: ContentType[] = [
  "post",
  "video",
  "reel",
  "article",
  "carousel",
  "story",
  "newsletter",
  "podcast",
];

export function DraftCard({
  item: initialItem,
  onChange,
  onCreated,
}: {
  item: ContentItemWithCompany;
  // Fired whenever this card's own item is updated in place (save,
  // approve/reject, quality check, …) — lets a parent that also holds
  // this item in a list (e.g. the workspace table) stay in sync instead
  // of going stale until a full refetch.
  onChange?: (item: ContentItemWithCompany) => void;
  // Fired when this card spawns a brand-new item (repurposing) — same
  // company as the source, so the parent can drop it straight into its
  // list instead of the caller needing to know to refetch.
  onCreated?: (item: ContentItemWithCompany) => void;
}) {
  const [item, setItem] = useState(initialItem);
  const [deciding, setDeciding] = useState(false);

  function applyUpdate(updated: Partial<ContentItemWithCompany>) {
    setItem((prev) => {
      const next = { ...prev, ...updated };
      onChange?.(next);
      return next;
    });
  }

  async function handleDecision(decision: "approved" | "rejected") {
    setDeciding(true);
    try {
      const updated = await updateContentItem(item.id, { approvalStatus: decision });
      applyUpdate(updated);
    } finally {
      setDeciding(false);
    }
  }
  const [draft, setDraft] = useState(item.draft_copy ?? "");
  const [hashtagsInput, setHashtagsInput] = useState((item.hashtags ?? []).join(", "));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [checkingQuality, setCheckingQuality] = useState(false);
  const [qualityCheckError, setQualityCheckError] = useState(false);

  const [historyOpen, setHistoryOpen] = useState(false);
  const [revisions, setRevisions] = useState<ContentItemRevision[] | null>(null);

  const [commentsOpen, setCommentsOpen] = useState(false);
  const [comments, setComments] = useState<ContentItemComment[] | null>(null);
  const [newComment, setNewComment] = useState("");
  const [postingComment, setPostingComment] = useState(false);

  const [briefOpen, setBriefOpen] = useState(false);
  const [briefLoaded, setBriefLoaded] = useState(false);
  const [brief, setBrief] = useState<ContentItemCreativeBrief | null>(null);
  const [generatingBrief, setGeneratingBrief] = useState(false);
  const [briefError, setBriefError] = useState(false);

  const [repurposeOpen, setRepurposeOpen] = useState(false);
  const [repurposePlatform, setRepurposePlatform] = useState<Platform>("instagram");
  const [repurposeContentType, setRepurposeContentType] = useState<ContentType>("post");
  const [repurposing, setRepurposing] = useState(false);
  const [repurposeError, setRepurposeError] = useState(false);
  const [repurposeResult, setRepurposeResult] = useState<ContentItem | null>(null);

  const hashtagsArray = hashtagsInput
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);
  const dirty =
    draft !== (item.draft_copy ?? "") ||
    hashtagsInput.trim() !== (item.hashtags ?? []).join(", ");

  async function handleCheckQuality() {
    setCheckingQuality(true);
    setQualityCheckError(false);
    try {
      const updated = await checkContentItemQuality(item.id);
      applyUpdate(updated);
    } catch {
      setQualityCheckError(true);
    } finally {
      setCheckingQuality(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      const updated = await updateContentItem(item.id, {
        draftCopy: draft,
        hashtags: hashtagsArray,
      });
      applyUpdate(updated);
      setHashtagsInput((updated.hashtags ?? []).join(", "));
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  async function toggleHistory() {
    const next = !historyOpen;
    setHistoryOpen(next);
    if (next && revisions === null) {
      const res = await listContentItemRevisions(item.id);
      setRevisions(res.items);
    }
  }

  async function toggleComments() {
    const next = !commentsOpen;
    setCommentsOpen(next);
    if (next && comments === null) {
      const res = await listContentItemComments(item.id);
      setComments(res.items);
    }
  }

  async function toggleBrief() {
    const next = !briefOpen;
    setBriefOpen(next);
    if (next && !briefLoaded) {
      try {
        setBrief(await getContentItemCreativeBrief(item.id));
      } catch {
        setBrief(null);
      } finally {
        setBriefLoaded(true);
      }
    }
  }

  async function handleGenerateBrief() {
    setGeneratingBrief(true);
    setBriefError(false);
    try {
      setBrief(await generateContentItemCreativeBrief(item.id));
      setBriefLoaded(true);
    } catch {
      setBriefError(true);
    } finally {
      setGeneratingBrief(false);
    }
  }

  async function handleRepurpose() {
    setRepurposing(true);
    setRepurposeError(false);
    setRepurposeResult(null);
    try {
      const created = await repurposeContentItem(item.id, repurposePlatform, repurposeContentType);
      setRepurposeResult(created);
      // Repurposing always lands in the source item's own company (see
      // the backend's repurpose endpoint) — carry that over rather than
      // asking the caller to look it up.
      onCreated?.({ ...created, company_id: item.company_id, company_name: item.company_name });
    } catch {
      setRepurposeError(true);
    } finally {
      setRepurposing(false);
    }
  }

  async function handlePostComment() {
    if (!newComment.trim()) return;
    setPostingComment(true);
    try {
      const comment = await createContentItemComment(item.id, newComment.trim());
      setComments((prev) => [...(prev ?? []), comment]);
      setNewComment("");
    } finally {
      setPostingComment(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{item.title}</p>
          <p className="text-xs text-muted-foreground">
            {item.company_name ?? "Unknown company"} · {item.suggested_date}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge variant="outline" className="capitalize">
            {item.approval_status}
          </Badge>
          {item.approval_status !== "approved" && (
            <Button
              size="icon-sm"
              variant="ghost"
              onClick={() => handleDecision("approved")}
              disabled={deciding}
              aria-label="Approve"
              title="Approve"
            >
              <Check className="h-3.5 w-3.5 text-primary" />
            </Button>
          )}
          {item.approval_status !== "rejected" && (
            <Button
              size="icon-sm"
              variant="ghost"
              onClick={() => handleDecision("rejected")}
              disabled={deciding}
              aria-label="Reject"
              title="Reject"
            >
              <XIcon className="h-3.5 w-3.5 text-destructive" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <textarea
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setSaved(false);
          }}
          rows={4}
          placeholder="No draft yet — write one here."
          className="w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />

        <input
          value={hashtagsInput}
          onChange={(e) => {
            setHashtagsInput(e.target.value);
            setSaved(false);
          }}
          placeholder="Hashtags, comma-separated (no # needed)"
          className="w-full rounded-md border border-input bg-transparent px-3 py-1.5 text-xs text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />

        <div className="flex items-center gap-2">
          <Button size="sm" onClick={handleSave} disabled={!dirty || saving}>
            {saving ? "Saving…" : saved ? "Saved" : "Save"}
          </Button>

          <Button size="sm" variant="ghost" onClick={toggleHistory}>
            <History className="h-3.5 w-3.5" />
            History
            {historyOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </Button>

          <Button size="sm" variant="ghost" onClick={toggleComments}>
            <MessageSquare className="h-3.5 w-3.5" />
            Comments{comments && comments.length > 0 ? ` (${comments.length})` : ""}
            {commentsOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </Button>

          <Button size="sm" variant="ghost" onClick={handleCheckQuality} disabled={checkingQuality || !item.draft_copy}>
            <ShieldCheck className="h-3.5 w-3.5" />
            {checkingQuality ? "Checking…" : "Check quality"}
          </Button>

          <Button size="sm" variant="ghost" onClick={toggleBrief}>
            <Clapperboard className="h-3.5 w-3.5" />
            Creative brief
            {briefOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </Button>

          <Button size="sm" variant="ghost" onClick={() => setRepurposeOpen((prev) => !prev)}>
            <Repeat2 className="h-3.5 w-3.5" />
            Repurpose
            {repurposeOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </Button>
        </div>

        {qualityCheckError && (
          <p className="text-xs text-destructive">Couldn&apos;t run the quality check — try again.</p>
        )}
        {item.quality_check_passed !== null && (
          <div
            className={`flex items-start gap-1.5 rounded-md border p-2 text-xs ${
              item.quality_check_passed
                ? "border-primary/30 bg-primary/5 text-foreground"
                : "border-destructive/30 bg-destructive/5 text-foreground"
            }`}
          >
            {item.quality_check_passed ? (
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" />
            )}
            <span>{item.quality_check_notes ?? (item.quality_check_passed ? "Looks good." : "Needs work.")}</span>
          </div>
        )}

        <PublishPanel item={item} />

        {historyOpen && (
          <div className="rounded-md border border-border p-3 text-xs">
            {revisions === null ? (
              <p className="text-muted-foreground">Loading…</p>
            ) : revisions.length === 0 ? (
              <p className="text-muted-foreground">No earlier versions.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {revisions.map((rev) => (
                  <li key={rev.id} className="border-b border-border/50 pb-2 last:border-0">
                    <p className="mb-1 text-muted-foreground">
                      {new Date(rev.created_at).toLocaleString()}
                      {rev.edited_by ? ` — ${rev.edited_by}` : ""}
                    </p>
                    <p className="whitespace-pre-wrap">{rev.draft_copy}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {commentsOpen && (
          <div className="rounded-md border border-border p-3 text-xs">
            {comments === null ? (
              <p className="text-muted-foreground">Loading…</p>
            ) : (
              <>
                {comments.length === 0 ? (
                  <p className="mb-2 text-muted-foreground">No comments yet.</p>
                ) : (
                  <ul className="mb-2 flex flex-col gap-2">
                    {comments.map((c) => (
                      <li key={c.id} className="border-b border-border/50 pb-2 last:border-0">
                        <p className="mb-1 text-muted-foreground">
                          {c.author ?? "Someone"} · {new Date(c.created_at).toLocaleString()}
                        </p>
                        <p>{c.body}</p>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex gap-2">
                  <input
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    placeholder="Add a comment…"
                    className="flex-1 rounded-md border border-input bg-transparent px-2 py-1 text-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring"
                  />
                  <Button
                    size="xs"
                    onClick={handlePostComment}
                    disabled={!newComment.trim() || postingComment}
                  >
                    Post
                  </Button>
                </div>
              </>
            )}
          </div>
        )}

        {briefOpen && (
          <div className="rounded-md border border-border p-3 text-xs">
            <div className="mb-2 flex items-center justify-between">
              <p className="font-medium text-foreground">Creative brief</p>
              <Button size="xs" onClick={handleGenerateBrief} disabled={generatingBrief}>
                {generatingBrief ? "Generating…" : brief ? "Regenerate" : "Generate brief"}
              </Button>
            </div>
            {briefError && (
              <p className="mb-2 text-destructive">Couldn&apos;t generate a brief — try again.</p>
            )}
            {!brief ? (
              <p className="text-muted-foreground">
                No creative brief yet — generate one for a hook, shot list, and visual direction.
              </p>
            ) : (
              <div className="flex flex-col gap-2 text-foreground">
                <div>
                  <p className="font-medium text-muted-foreground">Hook</p>
                  <p>{brief.hook}</p>
                </div>
                <div>
                  <p className="font-medium text-muted-foreground">Shot list</p>
                  <ul className="list-inside list-disc">
                    {brief.shot_list.map((shot, i) => (
                      <li key={i}>{shot}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-medium text-muted-foreground">Visual references</p>
                  <p>{brief.visual_references}</p>
                </div>
                <div>
                  <p className="font-medium text-muted-foreground">Editing notes</p>
                  <p>{brief.editing_notes}</p>
                </div>
                {brief.thumbnail_concept && (
                  <div>
                    <p className="font-medium text-muted-foreground">Thumbnail concept</p>
                    <p>{brief.thumbnail_concept}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {repurposeOpen && (
          <div className="rounded-md border border-border p-3 text-xs">
            <p className="mb-2 font-medium text-foreground">Repurpose for another platform</p>
            <p className="mb-2 text-muted-foreground">
              Adapts this post&apos;s core message for a different platform/format — a new draft,
              not a copy-paste.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={repurposePlatform}
                onChange={(e) => setRepurposePlatform(e.target.value as Platform)}
                className="rounded-md border border-input bg-transparent px-2 py-1 text-xs text-foreground outline-none"
              >
                {REPURPOSE_PLATFORMS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <select
                value={repurposeContentType}
                onChange={(e) => setRepurposeContentType(e.target.value as ContentType)}
                className="rounded-md border border-input bg-transparent px-2 py-1 text-xs text-foreground outline-none"
              >
                {REPURPOSE_CONTENT_TYPES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <Button size="xs" onClick={handleRepurpose} disabled={repurposing || !item.draft_copy}>
                {repurposing ? "Repurposing…" : "Repurpose"}
              </Button>
            </div>
            {repurposeError && (
              <p className="mt-2 text-destructive">Couldn&apos;t repurpose this item — try again.</p>
            )}
            {repurposeResult && (
              <p className="mt-2 text-foreground">
                Created &quot;{repurposeResult.title}&quot; as a new draft — see it in the table above.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
