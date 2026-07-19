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

export type ReportStatus = "pending" | "complete" | "failed";

export interface TrendReport {
  id: string;
  company_id: string;
  status: ReportStatus;
  status_error: string | null;
  period_days: number;
  summary: string | null;
  key_themes: string[] | null;
  notable_trends_summary: string | null;
  content_opportunities: string | null;
  created_at: string;
}

export interface TrendReportListResponse {
  items: TrendReport[];
  total: number;
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

export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface ContentItem {
  id: string;
  title: string;
  description: string;
  content_type: ContentType;
  platform: Platform;
  theme: string | null;
  suggested_date: string;
  source_trend_id: string | null;
  audience_interest: string | null;
  seasonal_event: string | null;
  approval_status: ApprovalStatus;
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

export type LifecycleStage = "draft" | "scheduled" | "active" | "completed" | "archived";

export interface Campaign {
  id: string;
  company_id: string;
  content_plan_id: string | null;
  strategy_id: string | null;
  status: GenerationStatus;
  status_error: string | null;
  lifecycle_stage: LifecycleStage;
  name: string | null;
  objective: string | null;
  budget_allocation: string | null;
  success_metrics: string | null;
  start_date: string | null;
  end_date: string | null;
  created_at: string;
}

export interface CampaignListResponse {
  items: Campaign[];
  total: number;
}

export type CollaborationPriority = "low" | "medium" | "high";

export interface CollaborationIdea {
  id: string;
  collaborator_archetype: string;
  partnership_angle: string;
  outreach_template: string;
  priority: CollaborationPriority;
  rationale: string | null;
}

export interface Collaboration {
  id: string;
  company_id: string;
  strategy_id: string | null;
  status: GenerationStatus;
  status_error: string | null;
  created_at: string;
  ideas: CollaborationIdea[];
}

export interface CollaborationSummary {
  id: string;
  company_id: string;
  strategy_id: string | null;
  status: GenerationStatus;
  status_error: string | null;
  created_at: string;
}

export interface CollaborationListResponse {
  items: CollaborationSummary[];
  total: number;
}

// ---------------------------------------------------------------------------
// Competitor Research
// ---------------------------------------------------------------------------

export type ComparisonStatus = "not_started" | "pending" | "complete" | "failed";

export interface Competitor {
  id: string;
  company_id: string;
  url: string;
  name: string | null;
  status: CompanyStatus;
  status_error: string | null;
  industry: string | null;
  business_model: string | null;
  target_audience: string | null;
  brand_voice: string | null;
  unique_value_prop: string | null;
  summary: string | null;
  comparison_status: ComparisonStatus;
  comparison_status_error: string | null;
  product_pricing_comparison: string | null;
  marketing_strategy_analysis: string | null;
  competitive_gaps: string | null;
  strategic_recommendations: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompetitorListResponse {
  items: Competitor[];
  total: number;
}

export interface CompetitorCreatedResponse {
  id: string;
  company_id: string;
  url: string;
  status: CompanyStatus;
}

// ---------------------------------------------------------------------------
// Social Media Analyzer
// ---------------------------------------------------------------------------

export type SocialPlatform =
  | "instagram"
  | "facebook"
  | "twitter"
  | "linkedin"
  | "tiktok"
  | "youtube";

export type ConnectionStatus = "connected" | "disconnected" | "error" | "expired";

export interface PlatformConnection {
  // null for a not-yet-connected platform — the list endpoint always
  // returns one entry per known platform, connected or not.
  id: string | null;
  company_id: string;
  platform: SocialPlatform;
  status: ConnectionStatus;
  status_error: string | null;
  external_account_id: string | null;
  external_account_name: string | null;
  scopes: string | null;
  connected_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PlatformConnectionListResponse {
  items: PlatformConnection[];
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

export interface KnowledgeFreshness {
  company_id: string;
  document_count: number;
  last_ingested_at: string | null;
  staleness_days: number | null;
}

export interface KnowledgeAuditReport {
  id: string;
  company_id: string;
  status: ReportStatus;
  status_error: string | null;
  coverage_summary: string | null;
  identified_gaps: string | null;
  recommendations: string | null;
  document_count_at_generation: number;
  created_at: string;
}

export interface KnowledgeAuditReportListResponse {
  items: KnowledgeAuditReport[];
  total: number;
}

export interface KnowledgeDocument {
  id: string;
  source_type: string;
  source_url: string;
  content_preview: string;
  created_at: string;
}

export interface KnowledgeDocumentDetail {
  id: string;
  source_type: string;
  source_url: string;
  content: string;
  raw_metadata: Record<string, unknown>;
  created_at: string;
}

export interface KnowledgeDocumentListResponse {
  items: KnowledgeDocument[];
  total: number;
}

export interface IngestionResult {
  sources_processed: number;
  chunks_persisted: number;
}

// ---------------------------------------------------------------------------
// Fetch helper + call sites
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData bodies (file uploads) must NOT get a manual Content-Type —
  // the browser sets `multipart/form-data; boundary=...` itself, and
  // overriding it here would break multipart parsing on the backend.
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${API_V1}${path}`, {
    ...init,
    headers: isFormData ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
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

export function getTrendsByIds(ids: string[]): Promise<TrendListResponse> {
  if (ids.length === 0) return Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 });
  const query = new URLSearchParams();
  for (const id of ids) query.append("ids", id);
  query.set("limit", String(ids.length));
  return apiFetch<TrendListResponse>(`/trend-analyzer/?${query.toString()}`);
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
  days?: number,
): Promise<ContentPlan> {
  return apiFetch<ContentPlan>("/content-management/content-plans", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, strategy_id: strategyId, days }),
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

export function updateContentItem(
  itemId: string,
  updates: { approvalStatus?: ApprovalStatus; suggestedDate?: string },
): Promise<ContentItem> {
  return apiFetch<ContentItem>(`/content-management/content-items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify({
      approval_status: updates.approvalStatus,
      suggested_date: updates.suggestedDate,
    }),
  });
}

export function createCampaign(
  companyId: string,
  options: { contentPlanId?: string; strategyId?: string } = {},
): Promise<Campaign> {
  return apiFetch<Campaign>("/content-management/campaigns", {
    method: "POST",
    body: JSON.stringify({
      company_id: companyId,
      content_plan_id: options.contentPlanId,
      strategy_id: options.strategyId,
    }),
  });
}

export function getCampaign(id: string): Promise<Campaign> {
  return apiFetch<Campaign>(`/content-management/campaigns/${id}`);
}

export function listCampaigns(companyId?: string): Promise<CampaignListResponse> {
  return apiFetch<CampaignListResponse>(
    `/content-management/campaigns${toQueryString({ company_id: companyId })}`,
  );
}

export function updateCampaignLifecycle(
  id: string,
  lifecycleStage: LifecycleStage,
): Promise<Campaign> {
  return apiFetch<Campaign>(`/content-management/campaigns/${id}/lifecycle`, {
    method: "PATCH",
    body: JSON.stringify({ lifecycle_stage: lifecycleStage }),
  });
}

export function createCollaboration(
  companyId: string,
  strategyId?: string,
): Promise<Collaboration> {
  return apiFetch<Collaboration>("/content-management/collaborations", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, strategy_id: strategyId }),
  });
}

export function getCollaboration(id: string): Promise<Collaboration> {
  return apiFetch<Collaboration>(`/content-management/collaborations/${id}`);
}

export function listCollaborations(companyId?: string): Promise<CollaborationListResponse> {
  return apiFetch<CollaborationListResponse>(
    `/content-management/collaborations${toQueryString({ company_id: companyId })}`,
  );
}

// Competitor Research
export function createCompetitor(
  companyId: string,
  url: string,
  name?: string,
): Promise<CompetitorCreatedResponse> {
  return apiFetch<CompetitorCreatedResponse>("/competitor-research/competitors", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, url, name }),
  });
}

export function getCompetitor(id: string): Promise<Competitor> {
  return apiFetch<Competitor>(`/competitor-research/competitors/${id}`);
}

export function listCompetitors(companyId?: string): Promise<CompetitorListResponse> {
  return apiFetch<CompetitorListResponse>(
    `/competitor-research/competitors${toQueryString({ company_id: companyId })}`,
  );
}

export function generateComparison(competitorId: string): Promise<Competitor> {
  return apiFetch<Competitor>(`/competitor-research/competitors/${competitorId}/comparison`, {
    method: "POST",
  });
}

export function suggestCompetitorNames(
  companyId: string,
): Promise<{ suggestions: string[]; ok: boolean }> {
  return apiFetch<{ suggestions: string[]; ok: boolean }>("/competitor-research/suggestions", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId }),
  });
}

// Social Media Analyzer
export function listConnections(companyId: string): Promise<PlatformConnectionListResponse> {
  return apiFetch<PlatformConnectionListResponse>(
    `/social-media-analyzer/connections${toQueryString({ company_id: companyId })}`,
  );
}

// Not a fetch call — OAuth needs a real browser navigation so the
// platform's own login/consent screen can render and eventually redirect
// back. Callers render this as a plain <a href>, not an onClick handler.
export function getPlatformAuthorizeUrl(platform: SocialPlatform, companyId: string): string {
  return `${API_BASE_URL}${API_V1}/social-media-analyzer/connections/${platform}/authorize${toQueryString({ company_id: companyId })}`;
}

export function disconnectPlatform(connectionId: string): Promise<PlatformConnection> {
  return apiFetch<PlatformConnection>(`/social-media-analyzer/connections/${connectionId}`, {
    method: "DELETE",
  });
}

// Trend Outputs
export function createTrendReport(companyId: string, periodDays?: number): Promise<TrendReport> {
  return apiFetch<TrendReport>("/trend-analyzer/reports", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, period_days: periodDays }),
  });
}

export function getTrendReport(id: string): Promise<TrendReport> {
  return apiFetch<TrendReport>(`/trend-analyzer/reports/${id}`);
}

export function listTrendReports(companyId?: string): Promise<TrendReportListResponse> {
  return apiFetch<TrendReportListResponse>(
    `/trend-analyzer/reports${toQueryString({ company_id: companyId })}`,
  );
}

// Knowledge Manager
export function getKnowledgeFreshness(companyId: string): Promise<KnowledgeFreshness> {
  return apiFetch<KnowledgeFreshness>(
    `/knowledge-base/freshness${toQueryString({ company_id: companyId })}`,
  );
}

export function createAuditReport(companyId: string): Promise<KnowledgeAuditReport> {
  return apiFetch<KnowledgeAuditReport>("/knowledge-base/audit-reports", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId }),
  });
}

export function getAuditReport(id: string): Promise<KnowledgeAuditReport> {
  return apiFetch<KnowledgeAuditReport>(`/knowledge-base/audit-reports/${id}`);
}

export function listAuditReports(companyId?: string): Promise<KnowledgeAuditReportListResponse> {
  return apiFetch<KnowledgeAuditReportListResponse>(
    `/knowledge-base/audit-reports${toQueryString({ company_id: companyId })}`,
  );
}

// Knowledge Base — document dashboard
export function listDocuments(
  companyId: string,
  options: { sourceType?: string; limit?: number; offset?: number } = {},
): Promise<KnowledgeDocumentListResponse> {
  return apiFetch<KnowledgeDocumentListResponse>(
    `/knowledge-base/documents${toQueryString({
      company_id: companyId,
      source_type: options.sourceType,
      limit: options.limit,
      offset: options.offset,
    })}`,
  );
}

export function getDocument(id: string): Promise<KnowledgeDocumentDetail> {
  return apiFetch<KnowledgeDocumentDetail>(`/knowledge-base/documents/${id}`);
}

export function deleteDocument(id: string): Promise<KnowledgeDocumentDetail> {
  return apiFetch<KnowledgeDocumentDetail>(`/knowledge-base/documents/${id}`, {
    method: "DELETE",
  });
}

export function createManualDocument(
  companyId: string,
  title: string,
  content: string,
): Promise<IngestionResult> {
  return apiFetch<IngestionResult>("/knowledge-base/documents/manual", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, title, content }),
  });
}

export function uploadDocument(companyId: string, file: File): Promise<IngestionResult> {
  const formData = new FormData();
  formData.append("company_id", companyId);
  formData.append("file", file);
  return apiFetch<IngestionResult>("/knowledge-base/documents/upload", {
    method: "POST",
    body: formData,
  });
}

export function indexBlogFeeds(companyId: string, feedUrls: string[]): Promise<IngestionResult> {
  return apiFetch<IngestionResult>("/knowledge-base/documents/blog-index", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, feed_urls: feedUrls }),
  });
}
