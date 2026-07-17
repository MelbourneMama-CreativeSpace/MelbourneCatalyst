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
}

export function TrendFilters({
  currentSource,
  currentCategory,
  currentMinRelevance,
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

  return (
    <div className="flex flex-wrap items-center gap-3">
      <select
        className={selectClassName}
        value={currentSource ?? ""}
        onChange={(event) => updateParam("source", event.target.value)}
        aria-label="Filter by source"
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
