import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Trend } from "@/lib/api";

const SOURCE_LABELS: Record<string, string> = {
  google_trends: "Google Trends",
  reddit: "Reddit",
  rss: "RSS / News",
  youtube: "YouTube",
};

function formatRelativeTime(iso: string): string {
  const hours = Math.floor((Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60));
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function TrendCard({ trend }: { trend: Trend }) {
  return (
    <Card className="hover-lift">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <Badge variant="outline">{SOURCE_LABELS[trend.source] ?? trend.source}</Badge>
          {trend.category && <Badge>{trend.category}</Badge>}
        </div>
        <CardTitle className="line-clamp-2">
          <a href={trend.url} target="_blank" rel="noreferrer" className="hover:underline">
            {trend.title}
          </a>
        </CardTitle>
        {trend.insight && <CardDescription>{trend.insight}</CardDescription>}
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{formatRelativeTime(trend.discovered_at)}</span>
          {trend.score !== null && <span>score: {trend.score.toFixed(0)}</span>}
        </div>
      </CardContent>
    </Card>
  );
}
