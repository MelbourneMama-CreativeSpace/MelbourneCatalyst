"use client";

import { useRouter, useSearchParams } from "next/navigation";

const PERIODS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

const selectClassName =
  "h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

export function AnalysisPeriodFilter({ currentPeriodDays }: { currentPeriodDays: number }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function updatePeriod(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("period_days", value);
    router.push(`/analysis?${params.toString()}`);
  }

  return (
    <select
      className={selectClassName}
      value={String(currentPeriodDays)}
      onChange={(event) => updatePeriod(event.target.value)}
      aria-label="Filter by time period"
    >
      {PERIODS.map((period) => (
        <option key={period.value} value={period.value}>
          {period.label}
        </option>
      ))}
    </select>
  );
}
