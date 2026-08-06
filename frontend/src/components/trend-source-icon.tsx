import { AtSign, Camera, LineChart, MessagesSquare, Music2, PlayCircle, Rss } from "lucide-react";

import type { TrendSource } from "@/lib/api";

// Generic (not brand-mark) icons for where a trend was discovered — this
// is about the *source*, not "connect your account" the way
// social-icons.tsx's real brand marks are, so plain lucide glyphs here
// keep it visually lighter. No emoji anywhere in this app's UI.
const SOURCE_ICONS: Record<TrendSource, typeof LineChart> = {
  google_trends: LineChart,
  reddit: MessagesSquare,
  rss: Rss,
  youtube: PlayCircle,
  twitter: AtSign,
  instagram: Camera,
  tiktok: Music2,
};

export const SOURCE_LABELS: Record<TrendSource, string> = {
  google_trends: "Google Trends",
  reddit: "Reddit",
  rss: "RSS / News",
  youtube: "YouTube",
  twitter: "X / Twitter",
  instagram: "Instagram",
  tiktok: "TikTok",
};

export function TrendSourceIcon({
  source,
  className,
}: {
  source: TrendSource;
  className?: string;
}) {
  const Icon = SOURCE_ICONS[source] ?? LineChart;
  return <Icon className={className} aria-hidden="true" />;
}
