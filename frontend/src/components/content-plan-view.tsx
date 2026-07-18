import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ContentItem, ContentPlan } from "@/lib/api";

function formatDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function ContentPlanView({
  contentPlan,
  trendTitlesById,
}: {
  contentPlan: ContentPlan;
  trendTitlesById: Record<string, string>;
}) {
  const statusVariant = contentPlan.status === "complete" ? "default" : "outline";
  const sortedItems = [...contentPlan.items].sort((a, b) =>
    a.suggested_date.localeCompare(b.suggested_date),
  );

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Content calendar</h1>
        <Badge variant={statusVariant}>{contentPlan.status}</Badge>
      </div>

      {contentPlan.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Content plan generation failed
              {contentPlan.status_error ? `: ${contentPlan.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {contentPlan.status !== "failed" && sortedItems.length === 0 && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              {contentPlan.status === "complete"
                ? "No content items were generated."
                : "Generating content plan…"}
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        {sortedItems.map((item) => (
          <ContentItemCard
            key={item.id}
            item={item}
            trendTitle={item.source_trend_id ? trendTitlesById[item.source_trend_id] : undefined}
          />
        ))}
      </div>
    </div>
  );
}

function ContentItemCard({ item, trendTitle }: { item: ContentItem; trendTitle?: string }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{item.title}</CardTitle>
          <span className="text-sm text-muted-foreground">{formatDate(item.suggested_date)}</span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{item.platform}</Badge>
          <Badge variant="outline">{item.content_type}</Badge>
          {item.theme && <Badge variant="default">{item.theme}</Badge>}
        </div>
        <p className="text-sm leading-relaxed">{item.description}</p>
        {trendTitle && (
          <p className="text-xs text-muted-foreground">Inspired by trend: {trendTitle}</p>
        )}
      </CardContent>
    </Card>
  );
}
