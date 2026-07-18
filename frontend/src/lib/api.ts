/**
 * Typed client for the backend API (`backend/app/api/v1/**`).
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_V1 = "/api/v1";

// ---------------------------------------------------------------------------
// Trends
// ---------------------------------------------------------------------------

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
  relevance_score: number | null;
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

// ---------------------------------------------------------------------------
// Companies
// ---------------------------------------------------------------------------

export type CompanyStatus =
  | "pending"
  | "scraping"
  | "extracting"
  | "complete"
  | "complete_no_profile"
  | "failed";

export interface Company {
  id: string;
  url: string;
  name: string | null;
  status: CompanyStatus;
  status_error: string | null;
  industry: string | null;
  business_model: string | null;
  target_audience: string | null;
  brand_voice: string | null;
  unique_value_prop: string | null;
  niche_keywords: string[] | null;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyListResponse {
  items: Company[];
  total: number;
}

export interface CompanyCreatedResponse {
  id: string;
  url: string;
  status: CompanyStatus;
}

// ---------------------------------------------------------------------------
// Content Management
// ---------------------------------------------------------------------------

export type GenerationStatus = "pending" | "complete" | "failed";

export interface Strategy {
  id: string;
  company_id: string;
  status: GenerationStatus;
  status_error: string | null;
  summary: string | null;
  marketing_strategy: string | null;
  campaign_direction: string | null;
  growth_recommendations: string | null;
  business_suggestions: string | null;
  created_at: string;
}

export interface StrategyListResponse {
  items: Strategy[];
  total: number;
}

export type ContentType = "post" | "video" | "article" | "carousel" | "story";
export type Platform =
  | "instagram"
  | "linkedin"
  | "twitter"
  | "tiktok"
  | "youtube"
  | "blog"
  | "facebook";

export interface ContentItem {
  id: string;
  title: string;
  description: string;
  content_type: ContentType;
  platform: Platform;
  theme: string | null;
  suggested_date: string;
  source_trend_id: string | null;
}

export interface ContentPlan {
  id: string;
  company_id: string;
  strategy_id: string | null;
  status: GenerationStatus;
  status_error: string | null;
  created_at: string;
  items: ContentItem[];
}

export interface ContentPlanSummary {
  id: string;
  company_id: string;
  strategy_id: string | null;
  status: GenerationStatus;
  status_error: string | null;
  created_at: string;
}

export interface ContentPlanListResponse {
  items: ContentPlanSummary[];
  total: number;
}

// ---------------------------------------------------------------------------
// Knowledge Base
// ---------------------------------------------------------------------------

export interface SearchHit {
  document_id: string;
  source_type: string;
  source_url: string;
  content: string;
  similarity: number;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
}

// ---------------------------------------------------------------------------
// Fetch helper + call sites
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${API_V1}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

function toQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const s = query.toString();
  return s ? `?${s}` : "";
}

// Trends
export interface ListTrendsParams {
  source?: string;
  category?: string;
  since?: string;
  min_relevance?: number;
  limit?: number;
  offset?: number;
}

export function listTrends(params: ListTrendsParams = {}): Promise<TrendListResponse> {
  return apiFetch<TrendListResponse>(`/trend-analyzer/${toQueryString({ ...params })}`);
}

export function getTrend(id: string): Promise<Trend> {
  return apiFetch<Trend>(`/trend-analyzer/${id}`);
}

export function getSourceStatus(): Promise<SourceStatus[]> {
  return apiFetch<SourceStatus[]>("/trend-analyzer/sources");
}

export function triggerCollection(): Promise<CollectionRunResult> {
  return apiFetch<CollectionRunResult>("/trend-analyzer/collect", { method: "POST" });
}

// Companies
export function listCompanies(): Promise<CompanyListResponse> {
  return apiFetch<CompanyListResponse>("/companies/");
}

export function getCompany(id: string): Promise<Company> {
  return apiFetch<Company>(`/companies/${id}`);
}

export function createCompany(url: string): Promise<CompanyCreatedResponse> {
  return apiFetch<CompanyCreatedResponse>("/companies/", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

// Knowledge Base
export function searchKnowledgeBase(
  q: string,
  options: { company_id?: string; k?: number } = {},
): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(
    `/knowledge-base/search${toQueryString({ q, ...options })}`,
  );
}

// Content Management
export function createStrategy(companyId: string): Promise<Strategy> {
  return apiFetch<Strategy>("/content-management/strategies", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId }),
  });
}

export function getStrategy(id: string): Promise<Strategy> {
  return apiFetch<Strategy>(`/content-management/strategies/${id}`);
}

export function listStrategies(companyId?: string): Promise<StrategyListResponse> {
  return apiFetch<StrategyListResponse>(
    `/content-management/strategies${toQueryString({ company_id: companyId })}`,
  );
}

export function createContentPlan(
  companyId: string,
  strategyId?: string,
): Promise<ContentPlan> {
  return apiFetch<ContentPlan>("/content-management/content-plans", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, strategy_id: strategyId }),
  });
}

export function getContentPlan(id: string): Promise<ContentPlan> {
  return apiFetch<ContentPlan>(`/content-management/content-plans/${id}`);
}

export function listContentPlans(companyId?: string): Promise<ContentPlanListResponse> {
  return apiFetch<ContentPlanListResponse>(
    `/content-management/content-plans${toQueryString({ company_id: companyId })}`,
  );
}
