import Link from "next/link";
import { ArrowUpRight, TrendingUp, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getDashboardSummary, listRecommendedTrends } from "@/lib/api-server";

export default async function DashboardPage() {
  const [summary, trends] = await Promise.all([
    getDashboardSummary(),
    listRecommendedTrends(5),
  ]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <p className="mt-1 text-muted-foreground">
        What&apos;s happening across your clients right now.
      </p>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Trending topics — real data, no fabricated numbers */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-primary" />
              Trending topics
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trends.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing trending yet — check back after the next collection run.
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {trends.items.map((trend) => (
                  <li key={trend.id}>
                    <Link
                      href={`/trends?source=${trend.source}`}
                      className="flex items-start justify-between gap-2 text-sm hover:text-primary"
                    >
                      <span className="line-clamp-2">{trend.title}</span>
                      {trend.relevance_score !== null && (
                        <Badge className="shrink-0">
                          {Math.round(trend.relevance_score * 100)}%
                        </Badge>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <Link
              href="/trends?recommended=1"
              className="mt-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              View all <ArrowUpRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>

        {/* Companies summary — real counts */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4 text-primary" />
              Your companies
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{summary.company_count}</p>
            <p className="text-sm text-muted-foreground">
              {summary.companies_onboarding > 0
                ? `${summary.companies_onboarding} still onboarding`
                : "All fully onboarded"}
            </p>
            {summary.recent_companies.length > 0 && (
              <ul className="mt-4 flex flex-col gap-2">
                {summary.recent_companies.map((company) => (
                  <li key={company.id}>
                    <Link
                      href={`/companies/${company.id}`}
                      className="flex items-center justify-between text-sm hover:text-primary"
                    >
                      <span className="truncate">{company.name ?? company.url}</span>
                      <Badge variant="outline" className="shrink-0 capitalize">
                        {company.status.replace(/_/g, " ")}
                      </Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <Link
              href="/companies"
              className="mt-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              View all <ArrowUpRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>

        {/* Performance — honest placeholder, not a fabricated number */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              No data yet — metric collection isn&apos;t wired up. Connect a
              platform from a company&apos;s page to start.
            </p>
            <Link
              href="/companies"
              className="mt-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Go to a company <ArrowUpRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
