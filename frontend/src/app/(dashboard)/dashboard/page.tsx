import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  FileEdit,
  Plus,
  TrendingUp,
  Users,
  AlertCircle,
  Building2,
  CalendarDays,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getDashboardSummary,
  listRecommendedTrends,
  listContentItems,
  listPendingApprovals,
} from "@/lib/api-server";
import { createClient } from "@/lib/supabase/server";
import type { ContentItemWithCompany } from "@/lib/api";

// ─── helpers ────────────────────────────────────────────────────────────────

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-AU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function platformLabel(p: string) {
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

function companyStatusBadge(status: string) {
  if (status === "complete")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-primary font-medium">
        <CheckCircle2 className="h-3 w-3" /> Active
      </span>
    );
  if (status === "failed")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive font-medium">
        <AlertCircle className="h-3 w-3" /> Failed
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground font-medium">
      <Clock className="h-3 w-3" /> Onboarding
    </span>
  );
}

// ─── page ────────────────────────────────────────────────────────────────────

export default async function DashboardPage() {
  const today = todayISO();

  // Fetch user name + all data in parallel
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const userName =
    (typeof user?.user_metadata?.full_name === "string" && user.user_metadata.full_name)
      ? (user.user_metadata.full_name as string).split(" ")[0]
      : user?.email?.split("@")[0] ?? null;

  // Fetch everything in parallel — each one silently falls back on error
  const [summary, trends, allItems, approvals] = await Promise.all([
    getDashboardSummary().catch(() => null),
    listRecommendedTrends(6).catch(() => null),
    listContentItems().catch(() => null),
    listPendingApprovals().catch(() => null),
  ]);

  // Derived cuts of content items
  const pendingDrafts =
    allItems?.items.filter((i) => i.approval_status === "pending" && i.draft_copy) ?? [];
  const scheduledToday =
    allItems?.items.filter(
      (i) => i.scheduled_at && i.scheduled_at.slice(0, 10) === today && !i.published_at,
    ) ?? [];
  const recentlyPublished =
    allItems?.items.filter((i) => i.published_at).slice(0, 5) ?? [];

  // Quick-action pill items
  const quickActions = [
    { label: "Create content", href: "/companies", icon: Plus },
    { label: "Create campaign", href: "/companies", icon: Zap },
    { label: "Add company", href: "/onboarding", icon: Building2 },
    { label: "Review drafts", href: "/companies", icon: FileEdit },
    { label: "Generate strategy", href: "/companies", icon: TrendingUp },
    { label: "Find trends", href: "/trends", icon: TrendingUp },
  ];

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-6 py-8 space-y-8">

        {/* ── Header ── */}
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-primary mb-1">
            Today's Command Center
          </p>
          <p className="text-sm text-muted-foreground">{formatDate(new Date().toISOString())}</p>
        </div>

        {/* ── Hero greeting card ── */}
        <div className="rounded-2xl border border-border bg-card px-8 py-7 shadow-sm">
          <h1 className="text-3xl font-semibold text-foreground mb-1">
            {greeting()}{userName ? `, ${userName}` : ""} 
          </h1>
          <p className="text-muted-foreground mb-6 text-sm">
            Here's what needs your attention today.
          </p>

          {/* Attention items */}
          <ul className="space-y-2.5 mb-6">
            {trends && trends.items.length > 0 && (
              <AttentionItem
                icon="🔥"
                text={`${trends.items.length} trending topics match your companies`}
                href="/trends"
              />
            )}
            {pendingDrafts.length > 0 && (
              <AttentionItem
                icon="📝"
                text={`${pendingDrafts.length} content draft${pendingDrafts.length > 1 ? "s" : ""} need review`}
                href="/companies"
              />
            )}
            {scheduledToday.length > 0 && (
              <AttentionItem
                icon="📅"
                text={`${scheduledToday.length} post${scheduledToday.length > 1 ? "s" : ""} scheduled today`}
                href="/companies"
              />
            )}
            {approvals && approvals.total > 0 && (
              <AttentionItem
                icon="✅"
                text={`${approvals.total} item${approvals.total > 1 ? "s" : ""} waiting for approval`}
                href="/approvals"
              />
            )}
            {summary && summary.companies_onboarding > 0 && (
              <AttentionItem
                icon="⚙️"
                text={`${summary.companies_onboarding} compan${summary.companies_onboarding > 1 ? "ies" : "y"} still onboarding`}
                href="/companies"
              />
            )}
            {!trends?.items.length &&
              !pendingDrafts.length &&
              !scheduledToday.length &&
              !approvals?.total &&
              !summary?.companies_onboarding && (
                <li className="text-sm text-muted-foreground">
                  Everything is up to date — no action needed right now.
                </li>
              )}
          </ul>

          {/* Recommended action */}
          {pendingDrafts.length > 0 && (
            <div className="flex items-center justify-between rounded-xl border border-border bg-muted/40 px-5 py-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-0.5">
                  Recommended Action
                </p>
                <p className="text-sm text-foreground">
                  Review {pendingDrafts[0].title} for{" "}
                  <span className="font-medium">{pendingDrafts[0].company_name ?? "your client"}</span>
                </p>
              </div>
              <Link
                href="/companies"
                className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity shrink-0 ml-4"
              >
                Review <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          )}
          {!pendingDrafts.length && (trends?.items.length ?? 0) > 0 && (
            <div className="flex items-center justify-between rounded-xl border border-border bg-muted/40 px-5 py-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-0.5">
                  Recommended Action
                </p>
                <p className="text-sm text-foreground">
                  Explore today's trending topics and create content
                </p>
              </div>
              <Link
                href="/trends"
                className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity shrink-0 ml-4"
              >
                View trends <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          )}
        </div>

        {/* ── Top 3 grid ── */}
        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">

          {/* Trending opportunities */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-sm font-semibold">
                <span className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  Trending Opportunities
                </span>
                <Link href="/trends" className="text-xs font-normal text-muted-foreground hover:text-primary flex items-center gap-0.5">
                  View all <ArrowRight className="h-3 w-3" />
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {!trends || trends.items.length === 0 ? (
                <NoData message="No trending topics yet — collection runs every few hours." />
              ) : (
                trends.items.slice(0, 5).map((t) => (
                  <div key={t.id} className="flex flex-col gap-0.5">
                    <a
                      href={t.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm font-medium text-foreground line-clamp-1 hover:text-primary transition-colors"
                    >
                      {t.title}
                    </a>
                    <p className="text-xs text-muted-foreground capitalize">
                      {t.source === "google_trends"
                        ? "↑ Rising on Google Trends"
                        : t.source === "reddit"
                        ? "🔥 Viral on Reddit"
                        : t.source === "rss"
                        ? "📰 In the news"
                        : `↑ ${t.source}`}
                    </p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {/* Today's pipeline */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-sm font-semibold">
                <span className="flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-primary" />
                  Today's Pipeline
                </span>
                <Link href="/companies" className="text-xs font-normal text-muted-foreground hover:text-primary flex items-center gap-0.5">
                  Open <ArrowRight className="h-3 w-3" />
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {scheduledToday.length === 0 && pendingDrafts.length === 0 ? (
                <NoData message="Nothing queued for today." />
              ) : (
                <>
                  {scheduledToday.slice(0, 3).map((item) => (
                    <PipelineItem key={item.id} item={item} tag="Scheduled" tagColor="teal" />
                  ))}
                  {pendingDrafts.slice(0, 3 - scheduledToday.length).map((item) => (
                    <PipelineItem key={item.id} item={item} tag="Draft" tagColor="slate" />
                  ))}
                </>
              )}
            </CardContent>
          </Card>

          {/* Company health */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-sm font-semibold">
                <span className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-primary" />
                  Company Health
                </span>
                <Link href="/companies" className="text-xs font-normal text-muted-foreground hover:text-primary flex items-center gap-0.5">
                  View all <ArrowRight className="h-3 w-3" />
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {!summary || summary.recent_companies.length === 0 ? (
                <NoData message="No companies yet — add your first client." />
              ) : (
                summary.recent_companies.slice(0, 3).map((c) => (
                  <div key={c.id} className="space-y-0.5">
                    <Link
                      href={`/companies/${c.id}`}
                      className="text-sm font-medium text-foreground hover:text-primary transition-colors"
                    >
                      {c.name ?? c.url}
                    </Link>
                    <div>{companyStatusBadge(c.status)}</div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Bottom 2-col grid ── */}
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">

          {/* Continue working — pending approvals + recent drafts */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Continue Working</CardTitle>
            </CardHeader>
            <CardContent>
              {(!approvals || approvals.items.length === 0) && pendingDrafts.length === 0 ? (
                <NoData message="Nothing pending — you're all caught up." />
              ) : (
                <ul className="divide-y divide-border">
                  {approvals?.items.slice(0, 5).map((a) => (
                    <li key={a.id}>
                      <Link
                        href={`/approvals`}
                        className="flex items-center justify-between py-2.5 text-sm text-foreground hover:text-primary transition-colors"
                      >
                        <span className="truncate flex-1 mr-2">{a.title}</span>
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      </Link>
                    </li>
                  ))}
                  {pendingDrafts.slice(0, 5 - (approvals?.items.length ?? 0)).map((d) => (
                    <li key={d.id}>
                      <Link
                        href={`/companies`}
                        className="flex items-center justify-between py-2.5 text-sm text-foreground hover:text-primary transition-colors"
                      >
                        <span className="truncate flex-1 mr-2">{d.title}</span>
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Quick actions */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2">
                {quickActions.map((action) => (
                  <Link
                    key={action.label}
                    href={action.href}
                    className="flex items-center gap-2 rounded-lg border border-border px-3 py-2.5 text-sm text-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-primary transition-colors"
                  >
                    <span className="text-primary font-bold text-base leading-none">+</span>
                    {action.label}
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ── Recently published ── */}
        {recentlyPublished.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <CheckCircle2 className="h-4 w-4 text-primary" />
                Recently Published
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y divide-border">
                {recentlyPublished.map((item) => (
                  <li key={item.id} className="flex items-center justify-between py-2.5 gap-4">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{item.title}</p>
                      <p className="text-xs text-muted-foreground">
                        {item.company_name ?? "Unknown"} · {platformLabel(item.platform)}
                        {item.published_at && (
                          <> · {new Date(item.published_at).toLocaleDateString()}</>
                        )}
                      </p>
                    </div>
                    <Badge variant="outline" className="shrink-0 capitalize text-primary border-primary/30">
                      Published
                    </Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

      </div>
    </div>
  );
}

// ─── sub-components ───────────────────────────────────────────────────────────

function AttentionItem({
  icon,
  text,
  href,
}: {
  icon: string;
  text: string;
  href: string;
}) {
  return (
    <li>
      <Link href={href} className="flex items-center gap-3 text-sm text-foreground hover:text-primary transition-colors">
        <span className="text-base leading-none shrink-0">{icon}</span>
        {text}
      </Link>
    </li>
  );
}

function PipelineItem({
  item,
  tag,
  tagColor,
}: {
  item: ContentItemWithCompany;
  tag: string;
  tagColor: "teal" | "slate";
}) {
  return (
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground line-clamp-1">{item.title}</p>
        <p className="text-xs text-muted-foreground">
          {item.company_name ?? "Unknown"} · {platformLabel(item.platform)}
        </p>
      </div>
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
          tagColor === "teal"
            ? "bg-primary/10 text-primary"
            : "bg-muted text-muted-foreground"
        }`}
      >
        {tag}
      </span>
    </div>
  );
}

function NoData({ message }: { message: string }) {
  return <p className="text-sm text-muted-foreground">{message}</p>;
}
