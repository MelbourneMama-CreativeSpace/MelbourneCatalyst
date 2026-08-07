"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { ChatPanel } from "@/components/chat-panel";
import { DraftCard } from "@/components/draft-card";
import {
  createConversation,
  getConversation,
  listCompanies,
  listContentItems,
  type ChatMessage,
  type Company,
  type ContentItemWithCompany,
  type Platform,
} from "@/lib/api";

const PLATFORMS: { value: Platform; label: string }[] = [
  { value: "linkedin", label: "LinkedIn" },
  { value: "instagram", label: "Instagram" },
  { value: "facebook", label: "Facebook" },
  { value: "twitter", label: "X / Twitter" },
  { value: "threads", label: "Threads" },
  { value: "tiktok", label: "TikTok" },
  { value: "youtube", label: "YouTube" },
  { value: "blog", label: "Blog" },
];

// A display-only status derived from real fields — there's no single
// "workflow status" column in the schema, just approval_status +
// scheduled_at + published_at + reviewer, each set independently. This
// is the one place that turns those into the single label/badge shown
// everywhere else on this page (stat cards, filters, table), so they
// can never drift out of sync with each other.
type WorkflowStatus = "draft" | "in_review" | "approved" | "rejected" | "scheduled" | "published";

const STATUS_META: Record<WorkflowStatus, { label: string; className: string }> = {
  draft: { label: "Draft", className: "border-border text-muted-foreground" },
  in_review: {
    label: "In review",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-700",
  },
  approved: { label: "Approved", className: "border-primary/30 bg-primary/10 text-primary" },
  rejected: {
    label: "Rejected",
    className: "border-destructive/30 bg-destructive/10 text-destructive",
  },
  scheduled: { label: "Scheduled", className: "border-accent/40 bg-accent/15 text-accent-foreground" },
  published: { label: "Published", className: "border-primary/30 bg-primary/10 text-primary" },
};

function workflowStatus(item: ContentItemWithCompany): WorkflowStatus {
  if (item.published_at) return "published";
  if (item.scheduled_at) return "scheduled";
  if (item.approval_status === "rejected") return "rejected";
  if (item.approval_status === "approved") return "approved";
  if (item.reviewer) return "in_review";
  return "draft";
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// This app manages one business's own content, not a roster of clients —
// so this page resolves straight to the one company on the account
// (`companies[0]`) instead of a "pick a client" list. Its full profile
// (industry, audience, brand voice — everything onboarding by URL
// produced) still lives at /companies/[id]; the "About {name}" link below
// goes there.
export default function ContentStudioPage() {
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const [items, setItems] = useState<ContentItemWithCompany[] | null>(null);
  const [error, setError] = useState(false);
  const [platformFilter, setPlatformFilter] = useState<Set<Platform>>(new Set());
  const [statusFilter, setStatusFilter] = useState<Set<WorkflowStatus>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationMessages, setConversationMessages] = useState<ChatMessage[]>([]);
  const [chatError, setChatError] = useState(false);

  const company = companies?.[0] ?? null;

  useEffect(() => {
    listContentItems()
      .then((res) => setItems(res.items))
      .catch(() => setError(true));
    listCompanies()
      .then((res) => setCompanies(res.items))
      .catch(() => setCompanies([]));
  }, []);

  useEffect(() => {
    if (!company) return;
    let cancelled = false;
    const storageKey = `loomverse:content-chat:${company.id}`;

    async function resolveConversation() {
      const savedId = localStorage.getItem(storageKey);
      if (savedId) {
        try {
          const detail = await getConversation(savedId);
          if (!cancelled) {
            setConversationId(detail.id);
            setConversationMessages(detail.messages);
          }
          return;
        } catch {
          // Saved conversation no longer exists (deleted, or from a
          // different account on this browser) — fall through and start
          // a fresh one instead of getting stuck.
          localStorage.removeItem(storageKey);
        }
      }
      const created = await createConversation(company!.id);
      localStorage.setItem(storageKey, created.id);
      if (!cancelled) {
        setConversationId(created.id);
        setConversationMessages([]);
      }
    }

    resolveConversation().catch(() => {
      if (!cancelled) setChatError(true);
    });
    return () => {
      cancelled = true;
    };
  }, [company]);

  function upsertItem(item: ContentItemWithCompany) {
    setItems((prev) => {
      if (!prev) return [item];
      const exists = prev.some((i) => i.id === item.id);
      return exists ? prev.map((i) => (i.id === item.id ? item : i)) : [item, ...prev];
    });
  }

  function refetchItems() {
    listContentItems()
      .then((res) => setItems(res.items))
      .catch(() => {
        // Leave whatever's already on screen — a failed refetch after a
        // chat action shouldn't wipe out a working table.
      });
  }

  const stats = useMemo(() => {
    const list = items ?? [];
    const now = new Date();
    const todayStr = now.toDateString();
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    let drafts = 0;
    let needsReview = 0;
    let scheduled = 0;
    let publishingToday = 0;
    let publishedThisWeek = 0;
    for (const item of list) {
      const status = workflowStatus(item);
      if (status === "draft") drafts += 1;
      if (status === "in_review") needsReview += 1;
      if (status === "scheduled") scheduled += 1;
      if (
        item.scheduled_at &&
        !item.published_at &&
        new Date(item.scheduled_at).toDateString() === todayStr
      ) {
        publishingToday += 1;
      }
      if (item.published_at && new Date(item.published_at) >= weekAgo) publishedThisWeek += 1;
    }
    return { drafts, needsReview, scheduled, publishingToday, publishedThisWeek };
  }, [items]);

  const platformCounts = useMemo(() => {
    const counts: Partial<Record<Platform, number>> = {};
    for (const item of items ?? []) counts[item.platform] = (counts[item.platform] ?? 0) + 1;
    return counts;
  }, [items]);

  const statusCounts = useMemo(() => {
    const counts: Partial<Record<WorkflowStatus, number>> = {};
    for (const item of items ?? []) {
      const status = workflowStatus(item);
      counts[status] = (counts[status] ?? 0) + 1;
    }
    return counts;
  }, [items]);

  const visibleItems = (items ?? []).filter((item) => {
    if (platformFilter.size > 0 && !platformFilter.has(item.platform)) return false;
    if (statusFilter.size > 0 && !statusFilter.has(workflowStatus(item))) return false;
    return true;
  });

  // Falls back to the unfiltered list so toggling a filter never yanks
  // away the panel for whatever's currently open.
  const selectedItem =
    visibleItems.find((i) => i.id === selectedId) ??
    (items ?? []).find((i) => i.id === selectedId) ??
    null;

  function togglePlatform(value: Platform) {
    setPlatformFilter((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  function toggleStatus(value: WorkflowStatus) {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Everything except the chat dock scrolls independently in here —
          the chat itself (below) never moves, so it's never scrolled out
          of view no matter how far down the table/filters go. */}
      <div className="flex-1 overflow-y-auto px-6 py-10">
        <div className="mx-auto max-w-6xl">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold">Content Studio</h1>
              <p className="mt-1 text-muted-foreground">
                Every piece of content, from idea to insight.
              </p>
            </div>
            {company && (
              <Link
                href={`/companies/${company.id}`}
                className="inline-flex h-9 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/80"
              >
                About {company.name ?? company.url ?? "this company"}
              </Link>
            )}
          </div>

          {companies === null && <p className="mt-6 text-sm text-muted-foreground">Loading…</p>}

          {companies !== null && !company && (
            <div className="mt-10 rounded-2xl border border-dashed border-border bg-muted/30 px-6 py-10 text-center">
              <p className="text-lg font-semibold">Set up your company</p>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                Add your website URL so LoomVerse AI understands what you do — industry,
                audience, brand voice — and this becomes your content hub.
              </p>
              <Link
                href="/onboarding"
                className="mt-4 inline-flex h-9 items-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/80"
              >
                Get started
              </Link>
            </div>
          )}

          {company && (
            <>
              <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
                <StatCard label="Drafts" value={stats.drafts} />
                <StatCard
                  label="Needs review"
                  value={stats.needsReview}
                  tone={stats.needsReview > 0 ? "warn" : undefined}
                />
                <StatCard label="Scheduled" value={stats.scheduled} />
                <StatCard
                  label="Publishing today"
                  value={stats.publishingToday}
                  tone={stats.publishingToday > 0 ? "accent" : undefined}
                />
                <StatCard label="Published this week" value={stats.publishedThisWeek} />
              </div>

              <div className="mt-6 flex flex-col gap-6 lg:flex-row">
                <aside className="w-full shrink-0 lg:w-56">
                  <FilterSection title="Platform">
                    {PLATFORMS.filter((p) => platformCounts[p.value]).map((p) => (
                      <FilterCheckbox
                        key={p.value}
                        label={p.label}
                        count={platformCounts[p.value] ?? 0}
                        checked={platformFilter.has(p.value)}
                        onChange={() => togglePlatform(p.value)}
                      />
                    ))}
                  </FilterSection>

                  <FilterSection title="Status">
                    {(Object.keys(STATUS_META) as WorkflowStatus[])
                      .filter((status) => statusCounts[status])
                      .map((status) => (
                        <FilterCheckbox
                          key={status}
                          label={STATUS_META[status].label}
                          count={statusCounts[status] ?? 0}
                          checked={statusFilter.has(status)}
                          onChange={() => toggleStatus(status)}
                        />
                      ))}
                  </FilterSection>
                </aside>

                <div className="min-w-0 flex-1">
                  {error && (
                    <p className="text-sm text-destructive">
                      Couldn&apos;t load content — try again.
                    </p>
                  )}
                  {!error && items === null && (
                    <p className="text-sm text-muted-foreground">Loading…</p>
                  )}
                  {!error && items !== null && items.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      No content yet — describe your first post in the chat below.
                    </p>
                  )}
                  {!error && items !== null && items.length > 0 && visibleItems.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      Nothing matches these filters yet.
                    </p>
                  )}

                  {visibleItems.length > 0 && (
                    <div className="overflow-x-auto rounded-lg border border-border">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                            <th className="px-4 py-2.5 font-medium">Title</th>
                            <th className="px-4 py-2.5 font-medium">Platform</th>
                            <th className="px-4 py-2.5 font-medium">Status</th>
                            <th className="px-4 py-2.5 font-medium">Quality</th>
                            <th className="px-4 py-2.5 font-medium">Date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleItems.map((item) => {
                            const status = workflowStatus(item);
                            const meta = STATUS_META[status];
                            const active = item.id === selectedId;
                            return (
                              <tr
                                key={item.id}
                                onClick={() => setSelectedId(active ? null : item.id)}
                                className={`cursor-pointer border-b border-border last:border-0 transition-colors ${
                                  active ? "bg-primary/5" : "hover:bg-muted/40"
                                }`}
                              >
                                <td className="max-w-[280px] truncate px-4 py-2.5 font-medium text-foreground">
                                  {item.title}
                                </td>
                                <td className="px-4 py-2.5 capitalize text-muted-foreground">
                                  {item.platform}
                                </td>
                                <td className="px-4 py-2.5">
                                  <span
                                    className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${meta.className}`}
                                  >
                                    {meta.label}
                                  </span>
                                </td>
                                <td className="px-4 py-2.5">
                                  {item.quality_check_passed === null ? (
                                    <span className="text-muted-foreground">—</span>
                                  ) : item.quality_check_passed ? (
                                    <CheckCircle2 className="h-4 w-4 text-primary" />
                                  ) : (
                                    <AlertTriangle className="h-4 w-4 text-destructive" />
                                  )}
                                </td>
                                <td className="px-4 py-2.5 text-muted-foreground">
                                  {formatDate(
                                    item.published_at ?? item.scheduled_at ?? item.suggested_date,
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {selectedItem && (
                    <div className="mt-4">
                      <DraftCard
                        key={selectedItem.id}
                        item={selectedItem}
                        onChange={upsertItem}
                        onCreated={upsertItem}
                      />
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* The same chat used at /chat, just scoped to this company — a tool
          call it makes to create/approve/reject/regenerate/publish/
          schedule content defaults to this company_id, so nothing here has
          to ask which client something is for. Fixed to the bottom of the
          viewport, not the page — it stays put while the content above
          scrolls. */}
      {company && (
        <div className="h-[420px] shrink-0 border-t border-border bg-background">
          {chatError && (
            <p className="px-6 py-4 text-sm text-destructive">
              Couldn&apos;t start a chat session — try refreshing.
            </p>
          )}
          {!chatError && !conversationId && (
            <p className="px-6 py-4 text-sm text-muted-foreground">Loading…</p>
          )}
          {conversationId && (
            <ChatPanel
              key={conversationId}
              conversationId={conversationId}
              initialMessages={conversationMessages}
              onActionConfirmed={refetchItems}
            />
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "warn" | "accent";
}) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3">
      <p
        className={`text-2xl font-bold ${
          tone === "warn" ? "text-amber-600" : tone === "accent" ? "text-primary" : "text-foreground"
        }`}
      >
        {value}
      </p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      <div className="flex flex-col gap-1.5">{children}</div>
    </div>
  );
}

function FilterCheckbox({
  label,
  count,
  checked,
  onChange,
}: {
  label: string;
  count: number;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-2 text-sm">
      <span className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={checked}
          onChange={onChange}
          className="h-3.5 w-3.5 rounded border-input"
        />
        <span className={checked ? "text-foreground" : "text-muted-foreground"}>{label}</span>
      </span>
      <span className="text-xs text-muted-foreground">{count}</span>
    </label>
  );
}
