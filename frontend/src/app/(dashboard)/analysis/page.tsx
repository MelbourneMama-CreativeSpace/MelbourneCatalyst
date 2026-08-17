import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  Eye,
  Heart,
  Lightbulb,
  ListChecks,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
} from "lucide-react";

import { AnalysisPeriodFilter } from "@/components/analysis-period-filter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAnalysisOverview, listCompanies } from "@/lib/api-server";
import type { AnalysisOverview, BreakdownRow } from "@/lib/api";

const DEFAULT_PERIOD_DAYS = 30;

interface AnalysisPageProps {
  searchParams: Promise<{ period_days?: string }>;
}

function formatDate(): string {
  return new Date().toLocaleDateString("en-AU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function platformLabel(p: string): string {
  const map: Record<string, string> = {
    instagram: "Instagram",
    linkedin: "LinkedIn",
    twitter: "X / Twitter",
    tiktok: "TikTok",
    youtube: "YouTube",
    blog: "Blog",
    facebook: "Facebook",
    threads: "Threads",
  };
  return map[p] ?? p;
}

function contentTypeLabel(t: string): string {
  return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default async function AnalysisPage({ searchParams }: AnalysisPageProps) {
  const { period_days } = await searchParams;
  const periodDays = Number(period_days) || DEFAULT_PERIOD_DAYS;

  // Same "one business per account" resolution as /trends and /companies —
  // no client roster, so there's nothing to pick between.
  const companiesRes = await listCompanies().catch(() => ({ items: [], total: 0 }));
  const company = companiesRes.items[0] ?? null;

  const overview = company
    ? await getAnalysisOverview(company.id, periodDays).catch(() => null)
    : null;

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-6 py-10 space-y-6">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-primary">
              Performance Analysis
            </p>
            <p className="text-sm text-muted-foreground">{formatDate()}</p>
          </div>
          {overview && <AnalysisPeriodFilter currentPeriodDays={periodDays} />}
        </div>

        {!company ? (
          <Card>
            <CardContent className="py-10 text-center">
              <p className="mb-1 text-lg font-semibold text-foreground">No company yet</p>
              <p className="mb-4 text-sm text-muted-foreground">
                Add your company to start seeing real performance analysis.
              </p>
              <Link
                href="/onboarding"
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity"
              >
                Add a company
              </Link>
            </CardContent>
          </Card>
        ) : !overview ? (
          <Card>
            <CardContent className="py-10 text-center">
              <p className="text-sm text-muted-foreground">
                Couldn&apos;t load analysis right now — try refreshing the page.
              </p>
            </CardContent>
          </Card>
        ) : (
          <AnalysisContent overview={overview} companyName={company.name ?? company.url ?? "this company"} />
        )}
      </div>
    </div>
  );
}

function AnalysisContent({
  overview,
  companyName,
}: {
  overview: AnalysisOverview;
  companyName: string;
}) {
  const hasLinkedIn = overview.by_platform.some((r) => r.key === "linkedin");

  return (
    <div className="space-y-6">
      {!overview.metrics_available && overview.posts_published > 0 && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="py-4 text-sm text-amber-800">
            {overview.posts_published} post{overview.posts_published === 1 ? "" : "s"} published
            this period, but no metrics have synced yet — the metrics sync job runs every few
            hours. Check back soon for real numbers.
          </CardContent>
        </Card>
      )}

      {overview.posts_published === 0 && (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="mb-1 text-lg font-semibold text-foreground">
              Nothing published for {companyName} in this period
            </p>
            <p className="text-sm text-muted-foreground">
              Publish some content, or widen the time range above, to see real analysis here.
            </p>
          </CardContent>
        </Card>
      )}

      {/* ── How are we doing? ── */}
      <section className="space-y-3">
        <SectionHeading icon={BarChart3} title="How are we doing?" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            icon={ListChecks}
            label="Posts Published"
            value={overview.posts_published}
            caption={
              overview.posts_failed > 0
                ? `${overview.posts_failed} rejected, not counted`
                : `over the last ${overview.period_days} days`
            }
          />
          <StatCard
            icon={Heart}
            label="Engagement"
            value={overview.current_totals.engagement}
            changePct={overview.engagement_change_pct}
            caption="likes + comments + shares + saves"
          />
          <StatCard
            icon={Eye}
            label="Reach"
            value={overview.current_totals.reach}
            changePct={overview.reach_change_pct}
            caption="not exposed by every platform"
          />
          <StatCard
            icon={TrendingUp}
            label="Avg Engagement / Post"
            value={
              overview.current_totals.posts > 0
                ? Math.round(overview.current_totals.engagement / overview.current_totals.posts)
                : 0
            }
            caption="per published post"
          />
        </div>
      </section>

      {/* ── What worked? / What didn't? ── */}
      {(overview.best_platform || overview.best_content_type || overview.best_topic) && (
        <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <ThumbsUp className="h-4 w-4 text-primary" />
                What worked
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5">
              <WinnerRow label="Best platform" value={overview.best_platform} formatter={platformLabel} />
              <WinnerRow
                label="Best content type"
                value={overview.best_content_type}
                formatter={contentTypeLabel}
              />
              <WinnerRow label="Best topic" value={overview.best_topic} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <ThumbsDown className="h-4 w-4 text-muted-foreground" />
                What didn&apos;t
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5">
              <WinnerRow label="Weakest platform" value={overview.worst_platform} formatter={platformLabel} />
              <WinnerRow
                label="Weakest content type"
                value={overview.worst_content_type}
                formatter={contentTypeLabel}
              />
              <WinnerRow label="Weakest topic" value={overview.worst_topic} />
            </CardContent>
          </Card>
        </section>
      )}

      {/* ── Why? / What should we do next? ── */}
      {(overview.ai_why || overview.ai_recommendations.length > 0) && (
        <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Lightbulb className="h-4 w-4 text-primary" />
                Why
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-foreground">
                {overview.ai_why ?? "Not enough data yet for an AI-generated explanation."}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="h-4 w-4 text-primary" />
                What should we do next
              </CardTitle>
            </CardHeader>
            <CardContent>
              {overview.ai_recommendations.length === 0 ? (
                <p className="text-sm text-muted-foreground">No recommendations yet.</p>
              ) : (
                <ul className="space-y-2">
                  {overview.ai_recommendations.map((rec, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                      {rec}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </section>
      )}

      {/* ── Breakdown tables ── */}
      {overview.by_platform.length > 0 && (
        <section className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <BreakdownCard title="By Platform" rows={overview.by_platform} formatter={platformLabel} />
          <BreakdownCard
            title="By Content Type"
            rows={overview.by_content_type}
            formatter={contentTypeLabel}
          />
          <BreakdownCard title="By Topic" rows={overview.by_topic} />
        </section>
      )}

      {hasLinkedIn && (
        <p className="text-xs text-muted-foreground">
          Note: LinkedIn currently only exposes reaction counts — comments, shares, and views
          aren&apos;t available from its API yet, so LinkedIn&apos;s engagement numbers above are
          understated relative to other platforms.
        </p>
      )}
    </div>
  );
}

// ─── sub-components ─────────────────────────────────────────────────────────

function SectionHeading({ icon: Icon, title }: { icon: typeof BarChart3; title: string }) {
  return (
    <h2 className="flex items-center gap-2 text-base font-semibold text-foreground">
      <Icon className="h-4 w-4 text-primary" />
      {title}
    </h2>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  changePct,
  caption,
}: {
  icon: typeof BarChart3;
  label: string;
  value: number | null;
  changePct?: number | null;
  caption: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <p className="text-3xl font-bold text-foreground">{value ?? "—"}</p>
        {changePct !== undefined && changePct !== null && (
          <span
            className={`flex items-center gap-0.5 text-xs font-medium ${
              changePct > 0
                ? "text-primary"
                : changePct < 0
                  ? "text-destructive"
                  : "text-muted-foreground"
            }`}
          >
            {changePct > 0 ? (
              <ArrowUp className="h-3 w-3" />
            ) : changePct < 0 ? (
              <ArrowDown className="h-3 w-3" />
            ) : null}
            {Math.abs(changePct)}%
          </span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">{caption}</p>
    </div>
  );
}

function WinnerRow({
  label,
  value,
  formatter,
}: {
  label: string;
  value: string | null;
  formatter?: (v: string) => string;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">
        {value ? (formatter ? formatter(value) : value) : "Not enough data yet"}
      </span>
    </div>
  );
}

function BreakdownCard({
  title,
  rows,
  formatter,
}: {
  title: string;
  rows: BreakdownRow[];
  formatter?: (v: string) => string;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No data yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {rows.map((row) => (
              <li key={row.key} className="flex items-center justify-between py-2 text-sm">
                <span className="text-foreground">
                  {formatter ? formatter(row.key) : row.key}
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    ({row.posts} post{row.posts === 1 ? "" : "s"})
                  </span>
                </span>
                <span className="font-medium text-foreground">
                  {row.avg_engagement} <span className="text-xs text-muted-foreground">avg</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
