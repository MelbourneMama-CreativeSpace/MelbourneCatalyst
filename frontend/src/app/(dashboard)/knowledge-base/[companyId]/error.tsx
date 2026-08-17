"use client";

import { ErrorState } from "@/components/error-state";

export default function KnowledgeBaseError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      title="Couldn't load the knowledge base"
      hint="We ran into a problem loading the knowledge base. Please try again in a moment."
      error={error}
      reset={reset}
      backHref="/companies"
      backLabel="Back to companies"
    />
  );
}
