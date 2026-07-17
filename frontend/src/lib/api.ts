/**
 * Typed client for the backend's Trend Analyzer API
 * (`backend/app/api/v1/endpoints/trends.py`).
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TREND_ANALYZER_PATH = "/api/v1/trend-analyzer";

export type TrendSource =
  | "google_trends"
  | "reddit"
  | "rss"
  | "youtube"
  | "twitter"
  | "instagram"
  | "tiktok";

export interface Trend {
  id: string;
  source: TrendSource;
  title: string;
  description: string | null;
  url: string;
  score: number | null;
  category: string | null;
  insight: string | null;
  discovered_at: string;
  created_at: string;
}

export interface TrendListResponse {
  items: Trend[];
  total: number;
  limit: number;
  offset: number;
}

export interface SourceStatus {
  source: string;
  total_stored: number;
  last_discovered_at: string | null;
  last_run_at: string | null;
  last_run_collected_count: number | null;
  last_run_new_items: number | null;
  last_run_error: string | null;
}

export interface CollectionSourceResult {
  source: string;
  collected_count: number;
  new_item_count: number;
  error: string | null;
  ran_at: string;
}

export interface CollectionRunResult {
  new_item_count: number;
  source_results: CollectionSourceResult[];
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${TREND_ANALYZER_PATH}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(`Trend Analyzer API error ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export interface ListTrendsParams {
  source?: string;
  category?: string;
  since?: string;
  limit?: number;
  offset?: number;
}

export function listTrends(params: ListTrendsParams = {}): Promise<TrendListResponse> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const queryString = query.toString();
  return apiFetch<TrendListResponse>(`/${queryString ? `?${queryString}` : ""}`);
}

export function getTrend(id: string): Promise<Trend> {
  return apiFetch<Trend>(`/${id}`);
}

export function getSourceStatus(): Promise<SourceStatus[]> {
  return apiFetch<SourceStatus[]>("/sources");
}

export function triggerCollection(): Promise<CollectionRunResult> {
  return apiFetch<CollectionRunResult>("/collect", { method: "POST" });
}
