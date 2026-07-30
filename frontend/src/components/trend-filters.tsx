"use client";

import { useRouter, useSearchParams } from "next/navigation";

const SOURCES = [
  { value: "", label: "All sources" },
  { value: "google_trends", label: "Google Trends" },
  { value: "reddit", label: "Reddit" },
  { value: "rss", label: "RSS / News" },
  { value: "youtube", label: "YouTube" },
  { value: "twitter", label: "X / Twitter" },
  { value: "instagram", label: "Instagram" },
  { value: "tiktok", label: "TikTok" },
];

const CATEGORIES = [
  "marketing",
  "technology",
  "business",
  "entertainment",
  "lifestyle",
  "sports",
  "politics",
  "health",
  "other",
  "uncategorized",
];

const RELEVANCE_THRESHOLDS = [
  { value: "", label: "Any relevance" },
  { value: "0.5", label: "≥ 50% match" },
  { value: "0.65", label: "≥ 65% match" },
  { value: "0.75", label: "≥ 75% match" },
  { value: "0.85", label: "≥ 85% match" },
];

const selectClassName =
  "h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

interface TrendFiltersProps {
  currentSource?: string;
  currentCategory?: string;
  currentMinRelevance?: string;
  currentRecommended?: boolean;
}

export function TrendFilters({
  currentSource,
  currentCategory,
  currentMinRelevance,
  currentRecommended,
}: TrendFiltersProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function updateParam(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    const queryString = params.toString();
    router.push(`/trends${queryString ? `?${queryString}` : ""}`);
  }

  function toggleRecommended() {
    // Recommended is its own view, not another filter dimension — the
    // backend endpoint ignores source/category/min_relevance entirely —
    // so switching it on clears the other filters rather than combining
    // with them.
    router.push(currentRecommended ? "/trends" : "/trends?recommended=1");
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={toggleRecommended}
        aria-pressed={currentRecommended}
        className={`h-8 rounded-lg border px-3 text-sm font-medium transition-colors ${
          currentRecommended
            ? "border-primary bg-primary/10 text-primary"
            : "border-input bg-transparent text-muted-foreground hover:text-foreground"
        }`}
      >
        Recommended
      </button>

      <select
        className={selectClassName}
        value={currentSource ?? ""}
        onChange={(event) => updateParam("source", event.target.value)}
        aria-label="Filter by source"
        disabled={currentRecommended}
      >
        {SOURCES.map((source) => (
          <option key={source.value} value={source.value}>
            {source.label}
          </option>
        ))}
      </select>

      <select
        className={selectClassName}
        value={currentCategory ?? ""}
        onChange={(event) => updateParam("category", event.target.value)}
        aria-label="Filter by category"
        disabled={currentRecommended}
      >
        <option value="">All categories</option>
        {CATEGORIES.map((category) => (
          <option key={category} value={category}>
            {category}
          </option>
        ))}
      </select>

      <select
        className={selectClassName}
        value={currentMinRelevance ?? ""}
        onChange={(event) => updateParam("min_relevance", event.target.value)}
        aria-label="Filter by minimum relevance"
        disabled={currentRecommended}
      >
        {RELEVANCE_THRESHOLDS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
