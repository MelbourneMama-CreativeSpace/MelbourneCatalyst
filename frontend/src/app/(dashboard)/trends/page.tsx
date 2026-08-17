import Link from "next/link";
import {
  Compass,
  Flame,
  RadioTower,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import { TrendFilters } from "@/components/trend-filters";
import { SOURCE_LABELS, TrendSourceIcon } from "@/components/trend-source-icon";
import { TriggerCollectionButton } from "@/components/trigger-collection-button";
import { getSourceStatus, listCompanies, listRecommendedTrends, listTrends } from "@/lib/api-server";
import { createClient } from "@/lib/supabase/server";
import type { Trend } from "@/lib/api";

// Real data only — no fabricated "up 31% today" style deltas. The Trend
// model has no time-series/velocity field, just a point-in-time
// relevance_score, so that's the only number shown, everywhere.
const HIGH_OPPORTUNITY_THRESHOLD = 0.85;

interface TrendsPageProps {
  searchParams: Promise<{
    source?: string;
    category?: string;
    min_relevance?: string;
    recommended?: string;
  }>;
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function formatDate(): string {
  return new Date().toLocaleDateString("en-AU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatRelativeTime(iso: string): string {
  const hours = Math.floor((Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60));
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default async function TrendsPage({ searchParams }: TrendsPageProps) {
  const { source, category, min_relevance, recommended } = await searchParams;
  const showRecommended = recommended === "1";
  const minRelevanceNumber = min_relevance ? Number(min_relevance) : undefined;

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const userName =
    typeof user?.user_metadata?.full_name === "string" && user.user_metadata.full_name
      ? (user.user_metadata.full_name as string).split(" ")[0]
      : (user?.email?.split("@")[0] ?? null);

  // This app manages one business's own trend-watching, not a roster of
  // clients — same single-company resolution as /companies. Relevance
  // scoring (both the feed and the stat cards below) uses that company's
  // own scores wherever a company exists, rather than the legacy global
  // ranking.
  const [companiesRes, sourceStatuses] = await Promise.all([
    listCompanies().catch(() => ({ items: [], total: 0 })),
    getSourceStatus().catch(() => []),
  ]);
  const company = companiesRes.items[0] ?? null;
  const companyId = company?.id;

  const [feed, highOpportunity, companyMatches] = await Promise.all([
    showRecommended
      ? listRecommendedTrends(undefined, companyId)
      : listTrends({
          source,
          category,
          min_relevance: Number.isFinite(minRelevanceNumber) ? minRelevanceNumber : undefined,
          company_id: companyId,
          limit: 24,
        }),
    listTrends({ min_relevance: HIGH_OPPORTUNITY_THRESHOLD, company_id: companyId, limit: 1 }).catch(
      () => null,
    ),
    companyId ? listRecommendedTrends(undefined, companyId).catch(() => null) : Promise.resolve(null),
  ]);

  const topicsTracked = sourceStatuses.reduce((sum, s) => sum + s.total_stored, 0);
  const platformCount = sourceStatuses.filter((s) => s.total_stored > 0).length;
  const highOpportunityCount = highOpportunity?.total ?? 0;
  const matchesCount = companyMatches?.items.length ?? 0;

  const narrative = company
    ? matchesCount > 0
      ? `${matchesCount} topic${matchesCount === 1 ? "" : "s"} ${matchesCount === 1 ? "is" : "are"} highly relevant to ${company.name ?? company.url} right now.`
      : `Nothing's cleared the relevance bar for ${company.name ?? company.url} yet — check back after the next collection run.`
    : topicsTracked > 0
      ? `${topicsTracked} topics tracked across ${platformCount} platform${platformCount === 1 ? "" : "s"}.`
      : "No trends collected yet — trigger a collection run to get started.";

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-6 py-10 space-y-6">
        {/* Header */}
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-primary">
            Trending Intelligence
          </p>
          <p className="text-sm text-muted-foreground">{formatDate()}</p>
        </div>

        {/* Greeting card */}
        <div className="rounded-2xl border border-border bg-card px-8 py-7 shadow-sm">
          <h1 className="mb-1 text-3xl font-semibold text-foreground">
            {greeting()}
            {userName ? `, ${userName}` : ""}
          </h1>
          <p className="mb-4 text-sm text-muted-foreground">Here&apos;s what&apos;s moving today.</p>
          <p className="mb-5 text-sm text-foreground">{narrative}</p>

          <div className="flex flex-wrap gap-2">
            <Pill icon={Flame} tone="warm">
              {highOpportunityCount} high opportunity
            </Pill>
            {company && (
              <Pill icon={Target} tone="primary">
                {matchesCount} recommended for {company.name ?? company.url}
              </Pill>
            )}
          </div>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            icon={TrendingUp}
            label="Topics tracked"
            value={topicsTracked}
            caption={`across ${platformCount} platform${platformCount === 1 ? "" : "s"}`}
          />
          <StatCard
            icon={Sparkles}
            label="High opportunity"
            value={highOpportunityCount}
            caption={`relevance above ${Math.round(HIGH_OPPORTUNITY_THRESHOLD * 100)}%`}
          />
          <StatCard
            icon={Target}
            label={company ? `Matches for ${company.name ?? "you"}` : "Matches"}
            value={matchesCount}
            caption={company ? "recommended today" : "add a company to personalize this"}
          />
        </div>

        {/* Feed + quick actions */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-foreground">Trending Feed</h2>
              <TrendFilters
                currentSource={source}
                currentCategory={category}
                currentMinRelevance={min_relevance}
                currentRecommended={showRecommended}
              />
            </div>

            {feed.items.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {showRecommended
                  ? "No trends meet the recommendation bar yet — check back after the next collection run."
                  : "No trends collected yet — trigger a collection run below."}
              </p>
            ) : (
              <div className="flex flex-col divide-y divide-border">
                {feed.items.map((trend) => (
                  <TrendRow key={trend.id} trend={trend} />
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-4">
            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <h2 className="mb-3 text-sm font-semibold text-foreground">Quick Actions</h2>
              <div className="flex flex-col gap-2">
                <QuickAction icon={Sparkles} label="Ask AI about these trends" href="/companies" />
                <QuickAction
                  icon={Compass}
                  label="Open Content Studio"
                  href="/companies"
                />
                {!company && (
                  <QuickAction icon={RadioTower} label="Add a company" href="/onboarding" />
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <h2 className="mb-3 text-sm font-semibold text-foreground">Sources</h2>
              {sourceStatuses.length === 0 ? (
                <p className="text-sm text-muted-foreground">No collection runs yet.</p>
              ) : (
                <ul className="flex flex-col gap-2.5">
                  {sourceStatuses.map((s) => (
                    <li key={s.source} className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex items-center gap-2 text-muted-foreground">
                        <TrendSourceIcon
                          source={s.source as Trend["source"]}
                          className="h-3.5 w-3.5 shrink-0"
                        />
                        {SOURCE_LABELS[s.source as Trend["source"]] ?? s.source}
                      </span>
                      <span className="font-medium text-foreground">{s.total_stored}</span>
                    </li>
                  ))}
                </ul>
              )}
              <TriggerCollectionButton />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TrendRow({ trend }: { trend: Trend }) {
  const pct = trend.relevance_score !== null ? Math.round(trend.relevance_score * 100) : null;
  return (
    <a
      href={trend.url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-4 py-3.5 first:pt-0 last:pb-0 group"
    >
      <TrendSourceIcon
        source={trend.source}
        className="h-5 w-5 shrink-0 text-primary"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground group-hover:text-primary transition-colors">
          {trend.title}
        </p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {SOURCE_LABELS[trend.source] ?? trend.source}
          {trend.category ? ` · ${trend.category}` : ""} · {formatRelativeTime(trend.discovered_at)}
        </p>
      </div>
      {pct !== null && (
        <div className="w-28 shrink-0">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-1 text-right text-xs text-muted-foreground">{pct}% match</p>
        </div>
      )}
    </a>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  caption,
}: {
  icon: typeof TrendingUp;
  label: string;
  value: number;
  caption: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <p className="text-3xl font-bold text-foreground">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{caption}</p>
    </div>
  );
}

function Pill({
  icon: Icon,
  tone,
  children,
}: {
  icon: typeof Flame;
  tone: "warm" | "primary";
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
        tone === "warm"
          ? "border-amber-500/30 bg-amber-500/10 text-amber-700"
          : "border-primary/30 bg-primary/10 text-primary"
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </span>
  );
}

function QuickAction({
  icon: Icon,
  label,
  href,
}: {
  icon: typeof Sparkles;
  label: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2.5 rounded-lg border border-border px-3 py-2.5 text-sm text-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-primary transition-colors"
    >
      <Icon className="h-4 w-4 shrink-0 text-primary" />
      {label}
    </Link>
  );
}
