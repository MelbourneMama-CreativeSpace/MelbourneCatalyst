"use client";

import { useRouter, useSearchParams } from "next/navigation";

const SOURCES = [
  { value: "", label: "All sources" },
  { value: "google_trends", label: "Google Trends" },
  { value: "reddit", label: "Reddit" },
  { value: "rss", label: "RSS / News" },
  { value: "youtube", label: "YouTube" },
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

const selectClassName =
  "h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

interface TrendFiltersProps {
  currentSource?: string;
  currentCategory?: string;
}

export function TrendFilters({ currentSource, currentCategory }: TrendFiltersProps) {
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
    </div>
  );
}
