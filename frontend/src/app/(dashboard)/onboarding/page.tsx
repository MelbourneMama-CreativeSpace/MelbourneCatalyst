"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createCompany } from "@/lib/api";

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <OnboardingForm />
    </Suspense>
  );
}

function OnboardingForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Set right after signup so first-time users land here with a welcome
  // framing and a way out; existing team members who click "Add a
  // client" from the sidebar skip straight to the plain form.
  const isPostSignup = searchParams.get("welcome") === "1";

  const [companyName, setCompanyName] = useState("");
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const trimmed = url.trim();
      const normalized = trimmed.startsWith("http") ? trimmed : `https://${trimmed}`;
      const created = await createCompany(normalized, companyName.trim());
      router.push(`/companies/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start onboarding");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-6 py-12">
      {!isPostSignup && (
        <Link href="/" className="mb-6 text-sm text-muted-foreground hover:text-foreground">
          &larr; Back
        </Link>
      )}
      <h1 className="text-3xl font-bold">
        {isPostSignup ? "Add your first company" : "Onboard a company"}
      </h1>
      <p className="mt-2 text-muted-foreground">
        Give us the company name and website URL. The Business Analyst agent will scrape the
        site and extract its industry, target audience, brand voice, and niche keywords &mdash;
        which every downstream agent uses to make decisions for you.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm text-muted-foreground">
          Company name
          <Input
            type="text"
            value={companyName}
            onChange={(event) => setCompanyName(event.target.value)}
            placeholder="Melbourne Mama"
            disabled={submitting}
            required
            className="h-12 text-base text-foreground"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm text-muted-foreground">
          Website URL
          <Input
            type="text"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="melbournemama.org"
            disabled={submitting}
            required
            className="h-12 text-base text-foreground"
          />
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button
          type="submit"
          disabled={submitting || !url.trim() || !companyName.trim()}
          className="h-12"
        >
          {submitting ? "Starting onboarding…" : "Analyze company"}
        </Button>
      </form>

      <p className="mt-6 text-xs text-muted-foreground">
        This typically takes ~30 seconds. You&apos;ll be redirected to a page that updates
        as the profile fills in.
      </p>

      {isPostSignup && (
        <Link
          href="/chat"
          className="mt-4 text-xs text-muted-foreground underline hover:text-foreground"
        >
          Skip for now — I&apos;ll add a company later
        </Link>
      )}
    </div>
  );
}
