"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CompetitorList } from "@/components/competitor-list";
import { ContentHistory } from "@/components/content-history";
import { createStrategy, getCompany, type Company } from "@/lib/api";

const TERMINAL_STATUSES: ReadonlySet<Company["status"]> = new Set([
  "complete",
  "complete_no_profile",
  "failed",
]);

export function CompanyProfile({ initialCompany }: { initialCompany: Company }) {
  const router = useRouter();
  const [company, setCompany] = useState(initialCompany);
  const [generatingStrategy, setGeneratingStrategy] = useState(false);
  const [strategyError, setStrategyError] = useState<string | null>(null);

  // Poll until the onboarding pipeline reaches a terminal status.
  useEffect(() => {
    if (TERMINAL_STATUSES.has(company.status)) return;
    const timer = setInterval(async () => {
      try {
        const fresh = await getCompany(company.id);
        setCompany(fresh);
        if (TERMINAL_STATUSES.has(fresh.status)) clearInterval(timer);
      } catch {
        // Transient network errors are fine — the next tick retries.
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [company.id, company.status]);

  async function handleGenerateStrategy() {
    setGeneratingStrategy(true);
    setStrategyError(null);
    try {
      const strategy = await createStrategy(company.id);
      router.push(`/strategy/${strategy.id}`);
    } catch (err) {
      setStrategyError(err instanceof Error ? err.message : "Failed to generate strategy.");
      setGeneratingStrategy(false);
    }
  }

  const statusVariant = company.status === "complete" ? "default" : "outline";

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">{company.name ?? company.url}</h1>
          <a
            href={company.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-muted-foreground hover:underline"
          >
            {company.url}
          </a>
        </div>
        <Badge variant={statusVariant}>{company.status}</Badge>
      </div>

      {company.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Onboarding failed{company.status_error ? `: ${company.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {company.status === "complete_no_profile" && (
        <Card>
          <CardContent className="pt-6">
            {/* A single template-literal expression, not JSX text adjacent
                to {expr} across line breaks — JSX collapses the leading
                whitespace of each text line, which silently ate the space
                after {company.url} when this was written as plain JSX text. */}
            <p className="text-sm text-muted-foreground">
              {`We scraped ${company.url} successfully, but couldn't generate a profile from it${
                company.status_error ? `: ${company.status_error}` : "."
              } You can re-run onboarding once that's fixed, from the same URL.`}
            </p>
          </CardContent>
        </Card>
      )}

      {!TERMINAL_STATUSES.has(company.status) && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              Analyzing the website. This usually takes ~30 seconds. This page updates as the
              agent completes each step (currently: <code>{company.status}</code>).
            </p>
          </CardContent>
        </Card>
      )}

      {company.summary && (
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed">{company.summary}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ProfileField label="Industry" value={company.industry} />
        <ProfileField label="Business model" value={company.business_model} />
        <ProfileField label="Target audience" value={company.target_audience} />
        <ProfileField label="Brand voice" value={company.brand_voice} />
        <ProfileField label="Unique value prop" value={company.unique_value_prop} full />
      </div>

      {company.niche_keywords && company.niche_keywords.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Niche keywords</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {company.niche_keywords.map((keyword) => (
                <Badge key={keyword} variant="outline">
                  {keyword}
                </Badge>
              ))}
            </div>
            <p className="mt-4 text-xs text-muted-foreground">
              The Trend Analyzer uses these keywords to score how relevant each trending
              topic is to your business.
            </p>
          </CardContent>
        </Card>
      )}

      {TERMINAL_STATUSES.has(company.status) && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-3">
            <Button render={<Link href="/trends">View matched trends</Link>} nativeButton={false} />
            {company.status === "complete" && (
              <Button variant="outline" onClick={handleGenerateStrategy} disabled={generatingStrategy}>
                {generatingStrategy ? "Generating strategy…" : "Generate strategy"}
              </Button>
            )}
          </div>
          {strategyError && <p className="text-sm text-destructive">{strategyError}</p>}
        </div>
      )}

      {company.status === "complete" && <CompetitorList companyId={company.id} />}

      {company.status === "complete" && <ContentHistory companyId={company.id} />}
    </div>
  );
}

function ProfileField({
  label,
  value,
  full,
}: {
  label: string;
  value: string | null;
  full?: boolean;
}) {
  return (
    <Card className={full ? "md:col-span-2" : undefined}>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm">{value ?? <span className="text-muted-foreground">—</span>}</p>
      </CardContent>
    </Card>
  );
}
