import Link from "next/link";

import { TrendCard } from "@/components/trend-card";
import { TrendFilters } from "@/components/trend-filters";
import { listTrends } from "@/lib/api";

interface TrendsPageProps {
  searchParams: Promise<{ source?: string; category?: string }>;
}

export default async function TrendsPage({ searchParams }: TrendsPageProps) {
  const { source, category } = await searchParams;
  const { items, total } = await listTrends({ source, category, limit: 24 });

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-6 py-12">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
              ← Back
            </Link>
            <h1 className="mt-2 text-3xl font-bold">Trend Analyzer</h1>
            <p className="mt-1 text-muted-foreground">
              {total} trending {total === 1 ? "topic" : "topics"} discovered across Google
              Trends, Reddit, RSS, and YouTube.
            </p>
          </div>
          <TrendFilters currentSource={source} currentCategory={category} />
        </div>

        {items.length === 0 ? (
          <p className="text-muted-foreground">
            No trends collected yet. Trigger a collection run via{" "}
            <code className="rounded bg-muted px-1.5 py-0.5">
              POST /api/v1/trend-analyzer/collect
            </code>
            .
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((trend) => (
              <TrendCard key={trend.id} trend={trend} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
