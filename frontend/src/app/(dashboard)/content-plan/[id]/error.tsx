"use client";

import { ErrorState } from "@/components/error-state";

export default function ContentPlanError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load this content plan"
      hint="We ran into a problem loading this content plan. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/companies"
      backLabel="Back to companies"
    />
  );
}
