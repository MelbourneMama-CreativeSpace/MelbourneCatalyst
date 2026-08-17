"use client";

import { ErrorState } from "@/components/error-state";

export default function CompetitorError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load this competitor"
      hint="We ran into a problem loading this competitor. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/companies"
      backLabel="Back to companies"
    />
  );
}
