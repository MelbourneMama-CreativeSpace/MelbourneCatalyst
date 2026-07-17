"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createCompany } from "@/lib/api";

export default function OnboardingPage() {
  const router = useRouter();
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
      const created = await createCompany(normalized);
      router.push(`/companies/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start onboarding");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-6 py-12">
      <Link href="/" className="mb-6 text-sm text-muted-foreground hover:text-foreground">
        &larr; Back
      </Link>
      <h1 className="text-3xl font-bold">Onboard your company</h1>
      <p className="mt-2 text-muted-foreground">
        Paste your company&apos;s website URL. The Business Analyst agent will scrape it and
        extract your industry, target audience, brand voice, and niche keywords &mdash;
        which every downstream agent uses to make decisions for you.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4">
        <Input
          type="text"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="melbournemama.org"
          disabled={submitting}
          required
          className="h-12 text-base"
        />
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={submitting || !url.trim()} className="h-12">
          {submitting ? "Starting onboarding…" : "Analyze company"}
        </Button>
      </form>

      <p className="mt-6 text-xs text-muted-foreground">
        This typically takes ~30 seconds. You&apos;ll be redirected to a page that updates
        as the profile fills in.
      </p>
    </div>
  );
}
