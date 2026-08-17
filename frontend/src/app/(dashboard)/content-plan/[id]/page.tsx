import Link from "next/link";
import { notFound } from "next/navigation";

import { ContentPlanView } from "@/components/content-plan-view";
import { ApiError } from "@/lib/api-error";
import { type ContentPlan } from "@/lib/api";
import { getContentPlan, getTrendsByIds } from "@/lib/api-server";

interface ContentPlanPageProps {
  params: Promise<{ id: string }>;
}

async function fetchContentPlanOrNotFound(id: string): Promise<ContentPlan> {
  try {
    return await getContentPlan(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
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
  if (trendIds.length === 0) return {};
  try {
    const { items } = await getTrendsByIds(trendIds);
    return Object.fromEntries(items.map((trend) => [trend.id, trend.title]));
  } catch {
    return {};
  }
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
