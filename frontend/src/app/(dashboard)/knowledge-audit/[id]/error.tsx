"use client";

import { ErrorState } from "@/components/error-state";

export default function KnowledgeAuditError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load this audit report"
      hint="We ran into a problem loading this audit report. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/companies"
      backLabel="Back to companies"
    />
  );
}
