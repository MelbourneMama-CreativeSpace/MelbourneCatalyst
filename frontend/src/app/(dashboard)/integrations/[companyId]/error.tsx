"use client";

import { ErrorState } from "@/components/error-state";

export default function IntegrationsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load social connections"
      hint="We ran into a problem loading your social connections. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/companies"
      backLabel="Back to companies"
    />
  );
}
