"use client";

import { ErrorState } from "@/components/error-state";

export default function CollaborationError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load this collaboration"
      hint="We ran into a problem loading this collaboration. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/companies"
      backLabel="Back to companies"
    />
  );
}
