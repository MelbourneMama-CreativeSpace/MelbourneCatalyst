"use client";

import { ErrorState } from "@/components/error-state";

export default function TrendsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load trends"
      hint="We ran into a problem loading trending topics. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/"
      backLabel="Back to home"
    />
  );
}
