import Link from "next/link";
import { notFound } from "next/navigation";

import { ContentPlanView } from "@/components/content-plan-view";
import { getContentPlan, getTrend, type ContentPlan } from "@/lib/api";

interface ContentPlanPageProps {
  params: Promise<{ id: string }>;
}

async function fetchContentPlanOrNotFound(id: string): Promise<ContentPlan> {
  try {
    return await getContentPlan(id);
  } catch (err) {
    if (err instanceof Error && err.message.includes("404")) {
      notFound();
    }
    throw err;
  }
}

async function resolveTrendTitles(contentPlan: ContentPlan): Promise<Record<string, string>> {
  const trendIds = [
    ...new Set(
      contentPlan.items
        .map((item) => item.source_trend_id)
        .filter((id): id is string => id !== null),
    ),
  ];
  const entries = await Promise.all(
    trendIds.map(async (id) => {
      try {
        const trend = await getTrend(id);
        return [id, trend.title] as const;
      } catch {
        return null;
      }
    }),
  );
  return Object.fromEntries(entries.filter((entry): entry is readonly [string, string] => entry !== null));
}

export default async function ContentPlanPage({ params }: ContentPlanPageProps) {
  const { id } = await params;
  const contentPlan = await fetchContentPlanOrNotFound(id);
  const trendTitlesById = await resolveTrendTitles(contentPlan);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/companies/${contentPlan.company_id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to company
        </Link>
        <ContentPlanView contentPlan={contentPlan} trendTitlesById={trendTitlesById} />
      </div>
    </div>
  );
}
