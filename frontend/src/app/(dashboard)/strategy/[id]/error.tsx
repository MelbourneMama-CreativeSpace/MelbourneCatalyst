"use client";

import { ErrorState } from "@/components/error-state";

export default function StrategyError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load this strategy"
      hint="We ran into a problem loading this strategy. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/companies"
      backLabel="Back to companies"
    />
  );
}
