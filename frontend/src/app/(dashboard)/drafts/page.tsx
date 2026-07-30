"use client";

import { useEffect, useState } from "react";

import { DraftCard } from "@/components/draft-card";
import { listContentItems, type ContentItemWithCompany, type Platform } from "@/lib/api";

const PLATFORMS: { value: Platform; label: string }[] = [
  { value: "instagram", label: "Instagram" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "twitter", label: "X / Twitter" },
  { value: "tiktok", label: "TikTok" },
  { value: "youtube", label: "YouTube" },
  { value: "facebook", label: "Facebook" },
  { value: "blog", label: "Blog" },
];

export default function DraftsWorkspacePage() {
  const [items, setItems] = useState<ContentItemWithCompany[] | null>(null);
  const [error, setError] = useState(false);
  const [activePlatform, setActivePlatform] = useState<Platform>("instagram");

  useEffect(() => {
    listContentItems()
      .then((res) => setItems(res.items))
      .catch(() => setError(true));
  }, []);

  const countsByPlatform = (items ?? []).reduce<Record<string, number>>((acc, item) => {
    acc[item.platform] = (acc[item.platform] ?? 0) + 1;
    return acc;
  }, {});

  const visibleItems = (items ?? []).filter((item) => item.platform === activePlatform);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-bold">Draft Workspace</h1>
      <p className="mt-1 text-muted-foreground">
        Every drafted post, organized by platform — edit in place, see version
        history, leave comments.
      </p>

      <div className="mt-6 flex flex-wrap gap-2 border-b border-border pb-4">
        {PLATFORMS.map((p) => (
          <button
            key={p.value}
            type="button"
            onClick={() => setActivePlatform(p.value)}
            className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
              activePlatform === p.value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground"
            }`}
          >
            {p.label}
            {countsByPlatform[p.value] ? ` (${countsByPlatform[p.value]})` : ""}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {error && (
          <p className="text-sm text-destructive">Couldn&apos;t load drafts — try again.</p>
        )}
        {!error && items === null && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {!error && items !== null && visibleItems.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No {PLATFORMS.find((p) => p.value === activePlatform)?.label} drafts yet.
          </p>
        )}
        <div className="flex flex-col gap-4">
          {visibleItems.map((item) => (
            <DraftCard key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
