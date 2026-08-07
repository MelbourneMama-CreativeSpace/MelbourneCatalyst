"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedUrl = url.trim();
  const trimmedDescription = description.trim();
  // Either input is enough on its own. A business with no website can still
  // describe itself, and that description is what the trend agents use to
  // work out its niche.
  const canSubmit = Boolean(companyName.trim()) && Boolean(trimmedUrl || trimmedDescription);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await createCompany({
        url: trimmedUrl
          ? trimmedUrl.startsWith("http")
            ? trimmedUrl
            : `https://${trimmedUrl}`
          : undefined,
        description: trimmedDescription || undefined,
        name: companyName.trim(),
      });
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
        Give us the company name, then a website, a description, or both. The Business
        Analyst agent extracts the industry, target audience, brand voice, and niche
        keywords &mdash; which every downstream agent uses to make decisions for you, and
        which determine what the trend agents go looking for.
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
          Website URL <span className="text-xs">(optional)</span>
          <Input
            type="text"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="melbournemama.org"
            disabled={submitting}
            className="h-12 text-base text-foreground"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm text-muted-foreground">
          What does the business do?{" "}
          <span className="text-xs">
            {trimmedUrl ? "(optional — adds context to the website)" : "(required — no website given)"}
          </span>
          <Textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="We run weekly pottery workshops for beginners in Brunswick, and sell handmade tableware at local markets."
            disabled={submitting}
            rows={4}
            className="text-base text-foreground"
          />
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={submitting || !canSubmit} className="h-12">
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
