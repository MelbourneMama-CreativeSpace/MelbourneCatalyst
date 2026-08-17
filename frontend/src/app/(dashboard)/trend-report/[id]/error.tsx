"use client";

import { ErrorState } from "@/components/error-state";

export default function TrendReportError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load this trend report"
      hint="We ran into a problem loading this trend report. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/companies"
      backLabel="Back to companies"
    />
  );
}
