/**
 * Typed client for the backend API (`backend/app/api/v1/**`).
 */

import {
  ApiError,
  API_CONFIRM_ACTION_TIMEOUT_MS,
  API_STREAM_IDLE_TIMEOUT_MS,
  API_TIMEOUT_MS,
  API_UPLOAD_TIMEOUT_MS,
  apiErrorFromNetworkFailure,
  apiErrorFromResponse,
  describeError,
} from "@/lib/api-error";

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
  campaign_alignment_notes: string | null;
  competitor_relevance_notes: string | null;
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
  // Null for a company onboarded from a typed description rather than a
  // website — not every business has one.
  url: string | null;
  description: string | null;
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
  products_and_services: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyListResponse {
  items: Company[];
  total: number;
}

/**
 * Someone with access to a company. `user_id` is null for an invite that
 * hasn't been claimed yet — that row grants nothing until the invited
 * person signs in with the matching email address.
 */
export interface CompanyMember {
  id: string;
  company_id: string;
  user_id: string | null;
  user_email: string | null;
  invited_email: string | null;
  role: string;
  created_at: string;
}

export interface CompanyMemberListResponse {
  items: CompanyMember[];
  /** Which of `items` is you — the browser never needs its own Supabase id. */
  current_user_id: string;
}

export interface CompanyCreatedResponse {
  id: string;
  url: string | null;
  name: string | null;
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
  approval_status: ApprovalStatus;
  approved_by: string | null;
  reviewer: string | null;
  created_at: string;
}

export interface StrategyListResponse {
  items: Strategy[];
  total: number;
}

export type ContentType =
  | "post"
  | "video"
  | "reel"
  | "article"
  | "carousel"
  | "story"
  | "newsletter"
  | "podcast";
export type Platform =
  | "instagram"
  | "linkedin"
  | "twitter"
  | "tiktok"
  | "youtube"
  | "blog"
  | "facebook"
  | "threads";

export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface ContentItem {
  id: string;
  title: string;
  description: string;
  draft_copy: string | null;
  hashtags: string[] | null;
  // A user-attached image/video URL — Instagram's real API has no
  // text-only post at all, so this is required before an Instagram item
  // can publish. Nothing in this app generates one; it's uploaded by hand
  // via uploadContentItemMedia(). Every other platform treats it as
  // optional decoration.
  media_url: string | null;
  repurposed_from_id: string | null;
  content_type: ContentType;
  platform: Platform;
  theme: string | null;
  suggested_date: string;
  source_trend_id: string | null;
  audience_interest: string | null;
  seasonal_event: string | null;
  approval_status: ApprovalStatus;
  approved_by: string | null;
  reviewer: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  quality_check_passed: boolean | null;
  quality_check_notes: string | null;
}

export interface ContentItemWithCompany extends ContentItem {
  company_id: string;
  company_name: string | null;
}

export interface ContentItemListResponse {
  items: ContentItemWithCompany[];
}

export interface ContentPlan {
  id: string;
  company_id: string;
  strategy_id: string | null;
  status: GenerationStatus;
  status_error: string | null;
  is_manual: boolean;
  created_at: string;
  items: ContentItem[];
}

export interface ContentPlanSummary {
  id: string;
  company_id: string;
  strategy_id: string | null;
  status: GenerationStatus;
  status_error: string | null;
  is_manual: boolean;
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
// Approval queue
// ---------------------------------------------------------------------------

export type PendingApprovalType = "strategy" | "content_item";

export interface PendingApproval {
  type: PendingApprovalType;
  id: string;
  company_id: string;
  company_name: string | null;
  title: string;
  reviewer: string | null;
  created_at: string;
}

export interface PendingApprovalListResponse {
  items: PendingApproval[];
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

// "pending" covers the moment between clicking Connect and Composio
// confirming the platform-side consent finished — the connections list
// refreshes it automatically once settled.
export type ConnectionStatus = "connected" | "pending" | "disconnected" | "error" | "expired";

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

export interface PlatformMetricSnapshot {
  id: string;
  platform_connection_id: string;
  captured_at: string;
  follower_count: number | null;
  engagement_rate: number | null;
}

export interface PlatformMetricSnapshotListResponse {
  items: PlatformMetricSnapshot[];
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
// Dashboard
// ---------------------------------------------------------------------------

export interface DashboardSummary {
  company_count: number;
  companies_onboarding: number;
  recent_companies: Company[];
  trending_topics: Trend[];
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface Conversation {
  id: string;
  company_id: string | null;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: Conversation[];
}

export interface ProposedAction {
  tool_name: string;
  tool_input: Record<string, unknown>;
  description: string;
  // Set only for the handful of write tools severe/irreversible enough
  // to need more than a single Confirm click (currently just deleting a
  // live post) — when present, the UI must require the user to type this
  // exact phrase before Confirm is even enabled. The real enforcement is
  // server-side in confirmAction; this is just what drives the UI gate.
  confirmation_phrase: string | null;
}

// Small structured snapshots a tool call surfaced this turn — the
// assistant referencing/creating a specific content item, or a trend —
// rendered as flashcards instead of only ever being described in prose.
export interface ContentItemCard {
  type: "content_item";
  id: string;
  company_id: string;
  title: string;
  platform: Platform;
  content_type: ContentType;
  draft_copy: string | null;
  hashtags: string[] | null;
  media_url: string | null;
  approval_status: ApprovalStatus;
  scheduled_at: string | null;
  published_at: string | null;
  // "preview" — just surfacing a draft that was created/found; no
  // publish/schedule controls, since nothing was actually asked to post.
  // "action" — this card is the preview attached to an actual
  // publish/schedule proposal, so publish/schedule controls belong here.
  card_context: "preview" | "action";
}

export interface TrendCard {
  type: "trend";
  id: string;
  title: string;
  source: string;
  url: string;
  category: string | null;
  insight: string | null;
  relevance_score: number | null;
}

export type ChatCard = ContentItemCard | TrendCard;

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls_summary: string[] | null;
  // Non-null when this message proposes a write action (approve/reject/
  // regenerate/publish/schedule) — never auto-executed, only run once the
  // user hits confirm via confirmAction below.
  proposed_action: ProposedAction | null;
  action_status: "pending" | "confirmed" | "cancelled" | null;
  cards: ChatCard[] | null;
  // Only meaningful on assistant messages — false means this is a
  // graceful-degradation reply (e.g. no Claude credit), not a real answer.
  // Absent on user messages.
  ok: boolean | null;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

// ---------------------------------------------------------------------------
// Fetch helper + call sites
// ---------------------------------------------------------------------------

// Every backend route requires a valid Supabase session (see
// backend/app/security/auth.py). This file is imported from Client
// Components (and re-exported types are used everywhere), so it can only
// ever reference the browser Supabase client — anything touching
// `next/headers` must live in api-server.ts instead, a separate module
// server components import directly. Turbopack traces static *and*
// dynamic imports into a file's client bundle regardless of runtime
// branching, so there's no safe way to make one shared function detect
// its environment here.
async function getAccessToken(): Promise<string | null> {
  const { createClient } = await import("@/lib/supabase/client");
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData bodies (file uploads) must NOT get a manual Content-Type —
  // the browser sets `multipart/form-data; boundary=...` itself, and
  // overriding it here would break multipart parsing on the backend.
  const isFormData = init?.body instanceof FormData;
  const token = await getAccessToken();
  const baseHeaders: Record<string, string> = {};
  if (!isFormData) baseHeaders["Content-Type"] = "application/json";
  if (token) baseHeaders["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_V1}${path}`, {
      ...init,
      headers: { ...baseHeaders, ...init?.headers },
      cache: "no-store",
      // Caller-supplied signal wins if one's ever passed in — none of
      // today's call sites do, but this stays correct if that changes.
      // Uploads get a longer budget than a plain JSON request (see
      // API_UPLOAD_TIMEOUT_MS) so a slow-but-genuine upload in progress
      // isn't misreported as a hung backend.
      signal:
        init?.signal ?? AbortSignal.timeout(isFormData ? API_UPLOAD_TIMEOUT_MS : API_TIMEOUT_MS),
    });
  } catch (cause) {
    // fetch() itself threw — the request never reached the server at all
    // (backend down, wrong NEXT_PUBLIC_API_URL, CORS, offline). Distinct
    // from the server responding with an error status below.
    throw apiErrorFromNetworkFailure(cause);
  }
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  return response.json() as Promise<T>;
}

export function toQueryString(params: Record<string, string | number | boolean | undefined>): string {
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
  // Scores `min_relevance` against this company's own relevance scores
  // instead of the legacy global score — omit for the global view.
  company_id?: string;
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

export function listRecommendedTrends(
  limit?: number,
  companyId?: string,
): Promise<TrendListResponse> {
  return apiFetch<TrendListResponse>(
    `/trend-analyzer/recommended${toQueryString({ limit, company_id: companyId })}`,
  );
}

export function getSourceStatus(): Promise<SourceStatus[]> {
  return apiFetch<SourceStatus[]>("/trend-analyzer/sources");
}

export function triggerCollection(): Promise<CollectionRunResult> {
  return apiFetch<CollectionRunResult>("/trend-analyzer/collect", { method: "POST" });
}

// Dashboard
export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>("/dashboard/summary");
}

// Companies
export function listCompanies(): Promise<CompanyListResponse> {
  return apiFetch<CompanyListResponse>("/companies/");
}

export function getCompany(id: string): Promise<Company> {
  return apiFetch<Company>(`/companies/${id}`);
}

/**
 * Start onboarding. Pass a website URL, a description of the business, or
 * both — the API rejects neither, since it would have nothing to build a
 * profile (and therefore the trend niche) from.
 */
export function createCompany(
  input: { url?: string; description?: string; name?: string },
): Promise<CompanyCreatedResponse> {
  return apiFetch<CompanyCreatedResponse>("/companies/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listCompanyMembers(
  companyId: string,
): Promise<CompanyMemberListResponse> {
  return apiFetch<CompanyMemberListResponse>(`/companies/${companyId}/members`);
}

export function inviteCompanyMember(
  companyId: string,
  email: string,
): Promise<CompanyMember> {
  return apiFetch<CompanyMember>(`/companies/${companyId}/members`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function removeCompanyMember(
  companyId: string,
  memberId: string,
): Promise<CompanyMember> {
  return apiFetch<CompanyMember>(`/companies/${companyId}/members/${memberId}`, {
    method: "DELETE",
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
export function listPendingApprovals(): Promise<PendingApprovalListResponse> {
  return apiFetch<PendingApprovalListResponse>("/content-management/approvals/pending");
}

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

export function updateStrategyApproval(
  strategyId: string,
  approvalStatus: ApprovalStatus,
  approvedBy?: string,
  reviewer?: string,
): Promise<Strategy> {
  return apiFetch<Strategy>(`/content-management/strategies/${strategyId}/approval`, {
    method: "PATCH",
    body: JSON.stringify({
      approval_status: approvalStatus,
      approved_by: approvedBy,
      reviewer,
    }),
  });
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

export function listContentItems(
  params: { companyId?: string; platform?: Platform } = {},
): Promise<ContentItemListResponse> {
  return apiFetch<ContentItemListResponse>(
    `/content-management/content-items${toQueryString({
      company_id: params.companyId,
      platform: params.platform,
    })}`,
  );
}

export function createManualContentItem(
  companyId: string,
  platform: Platform,
  contentType: ContentType,
  topic: string,
): Promise<ContentItem> {
  return apiFetch<ContentItem>(`/content-management/content-plans/${companyId}/manual-item`, {
    method: "POST",
    body: JSON.stringify({ platform, content_type: contentType, topic }),
  });
}

export function listContentPlans(companyId?: string): Promise<ContentPlanListResponse> {
  return apiFetch<ContentPlanListResponse>(
    `/content-management/content-plans${toQueryString({ company_id: companyId })}`,
  );
}

export function updateContentItem(
  itemId: string,
  updates: {
    approvalStatus?: ApprovalStatus;
    approvedBy?: string;
    suggestedDate?: string;
    draftCopy?: string;
    editedBy?: string;
    hashtags?: string[];
    reviewer?: string;
  },
): Promise<ContentItem> {
  return apiFetch<ContentItem>(`/content-management/content-items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify({
      approval_status: updates.approvalStatus,
      approved_by: updates.approvedBy,
      suggested_date: updates.suggestedDate,
      draft_copy: updates.draftCopy,
      edited_by: updates.editedBy,
      hashtags: updates.hashtags,
      reviewer: updates.reviewer,
    }),
  });
}

/** Attaches an image/video to a content item — required before an
 * Instagram item can publish (Instagram's real API has no text-only
 * post). Nothing in this app generates the image; the user supplies it. */
export function uploadContentItemMedia(itemId: string, file: File): Promise<ContentItem> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<ContentItem>(`/content-management/content-items/${itemId}/media`, {
    method: "POST",
    body: formData,
  });
}

export function removeContentItemMedia(itemId: string): Promise<ContentItem> {
  return apiFetch<ContentItem>(`/content-management/content-items/${itemId}/media`, {
    method: "DELETE",
  });
}

export interface ContentItemRevision {
  id: string;
  content_item_id: string;
  draft_copy: string;
  edited_by: string | null;
  created_at: string;
}

export interface ContentItemComment {
  id: string;
  content_item_id: string;
  author: string | null;
  body: string;
  created_at: string;
}

export function listContentItemRevisions(
  itemId: string,
): Promise<{ items: ContentItemRevision[] }> {
  return apiFetch<{ items: ContentItemRevision[] }>(
    `/content-management/content-items/${itemId}/revisions`,
  );
}

export function listContentItemComments(
  itemId: string,
): Promise<{ items: ContentItemComment[] }> {
  return apiFetch<{ items: ContentItemComment[] }>(
    `/content-management/content-items/${itemId}/comments`,
  );
}

export function createContentItemComment(
  itemId: string,
  body: string,
  author?: string,
): Promise<ContentItemComment> {
  return apiFetch<ContentItemComment>(`/content-management/content-items/${itemId}/comments`, {
    method: "POST",
    body: JSON.stringify({ body, author }),
  });
}

export function regenerateContentItemDraft(itemId: string): Promise<ContentItem> {
  return apiFetch<ContentItem>(`/content-management/content-items/${itemId}/regenerate-draft`, {
    method: "POST",
  });
}

export function repurposeContentItem(
  itemId: string,
  platform: Platform,
  contentType: ContentType,
): Promise<ContentItem> {
  return apiFetch<ContentItem>(`/content-management/content-items/${itemId}/repurpose`, {
    method: "POST",
    body: JSON.stringify({ platform, content_type: contentType }),
  });
}

export function checkContentItemQuality(itemId: string): Promise<ContentItem> {
  return apiFetch<ContentItem>(`/content-management/content-items/${itemId}/quality-check`, {
    method: "POST",
  });
}

export interface ContentItemCreativeBrief {
  id: string;
  content_item_id: string;
  hook: string | null;
  shot_list: string[];
  visual_references: string | null;
  editing_notes: string | null;
  thumbnail_concept: string | null;
  created_at: string;
  updated_at: string;
}

export function generateContentItemCreativeBrief(
  itemId: string,
): Promise<ContentItemCreativeBrief> {
  return apiFetch<ContentItemCreativeBrief>(
    `/content-management/content-items/${itemId}/creative-brief`,
    { method: "POST" },
  );
}

export function getContentItemCreativeBrief(
  itemId: string,
): Promise<ContentItemCreativeBrief> {
  return apiFetch<ContentItemCreativeBrief>(
    `/content-management/content-items/${itemId}/creative-brief`,
  );
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
// Async because the session has to ride along as a query param — plain
// navigation can't carry a custom Authorization header the way fetch()
// calls elsewhere in this file do.
export async function getPlatformAuthorizeUrl(
  platform: SocialPlatform,
  companyId: string,
): Promise<string> {
  const token = await getAccessToken();
  return `${API_BASE_URL}${API_V1}/social-media-analyzer/connections/${platform}/authorize${toQueryString({ company_id: companyId, access_token: token ?? undefined })}`;
}

export function disconnectPlatform(connectionId: string): Promise<PlatformConnection> {
  return apiFetch<PlatformConnection>(`/social-media-analyzer/connections/${connectionId}`, {
    method: "DELETE",
  });
}

export function getConnectionMetrics(
  connectionId: string,
): Promise<PlatformMetricSnapshotListResponse> {
  return apiFetch<PlatformMetricSnapshotListResponse>(
    `/social-media-analyzer/connections/${connectionId}/metrics`,
  );
}

export function syncConnectionMetrics(connectionId: string): Promise<PlatformMetricSnapshot> {
  return apiFetch<PlatformMetricSnapshot>(
    `/social-media-analyzer/connections/${connectionId}/sync-metrics`,
    { method: "POST" },
  );
}

export function generatePerformanceInsights(companyId: string): Promise<{ insights: string }> {
  return apiFetch<{ insights: string }>(
    `/social-media-analyzer/insights${toQueryString({ company_id: companyId })}`,
    { method: "POST" },
  );
}

export interface PublishResult {
  content_item_id: string;
  status: "success" | "failed";
  status_error: string | null;
  published_at: string | null;
  // Best-effort real link to the published post — null if the platform
  // has no permalink concept (e.g. this app couldn't resolve one) or the
  // lookup itself failed; never a sign the publish itself failed.
  post_url: string | null;
}

export function publishNow(
  connectionId: string,
  contentItemId: string,
): Promise<PublishResult> {
  return apiFetch<PublishResult>(`/social-media-analyzer/connections/${connectionId}/publish`, {
    method: "POST",
    body: JSON.stringify({ content_item_id: contentItemId }),
  });
}

export interface PublishAttempt {
  id: string;
  content_item_id: string;
  content_item_title: string;
  platform_connection_id: string;
  platform: string;
  company_id: string;
  company_name: string | null;
  status: "success" | "failed";
  status_error: string | null;
  composio_execution_id: string | null;
  attempted_at: string;
}

export function listPublishAttempts(filters: {
  companyId?: string;
  status?: string;
  platform?: string;
} = {}): Promise<{ items: PublishAttempt[] }> {
  return apiFetch<{ items: PublishAttempt[] }>(
    `/social-media-analyzer/publish-attempts${toQueryString({
      company_id: filters.companyId,
      status: filters.status,
      platform: filters.platform,
    })}`,
  );
}

export function retryPublishAttempt(attemptId: string): Promise<PublishResult> {
  return apiFetch<PublishResult>(
    `/social-media-analyzer/publish-attempts/${attemptId}/retry`,
    { method: "POST" },
  );
}

export function scheduleContentItem(
  itemId: string,
  scheduledAt: string | null,
): Promise<ContentItem> {
  return apiFetch<ContentItem>(`/content-management/content-items/${itemId}/schedule`, {
    method: "POST",
    body: JSON.stringify({ scheduled_at: scheduledAt }),
  });
}

// Trend Outputs
export function createTrendReport(companyId: string, periodDays?: number): Promise<TrendReport> {
  return apiFetch<TrendReport>("/trend-analyzer/reports", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, period_days: periodDays }),
  });
}

export interface Opportunity {
  title: string;
  reasoning: string;
  source: "trend" | "seasonal" | "performance" | "evergreen";
  priority: "high" | "medium" | "low";
}

export function generateContentOpportunities(
  companyId: string,
): Promise<{ items: Opportunity[] }> {
  return apiFetch<{ items: Opportunity[] }>(
    `/trend-analyzer/opportunities${toQueryString({ company_id: companyId })}`,
    { method: "POST" },
  );
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

// Chat
export function listConversations(companyId?: string): Promise<ConversationListResponse> {
  return apiFetch<ConversationListResponse>(
    `/chat/conversations${toQueryString({ company_id: companyId })}`,
  );
}

export function createConversation(companyId?: string): Promise<Conversation> {
  return apiFetch<Conversation>("/chat/conversations", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId }),
  });
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/chat/conversations/${id}`);
}

export function deleteConversation(id: string): Promise<Conversation> {
  return apiFetch<Conversation>(`/chat/conversations/${id}`, { method: "DELETE" });
}

export function sendMessage(conversationId: string, content: string): Promise<ChatMessage> {
  return apiFetch<ChatMessage>(`/chat/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function confirmAction(
  conversationId: string,
  messageId: string,
  confirmationText?: string,
): Promise<ChatMessage> {
  return apiFetch<ChatMessage>(
    `/chat/conversations/${conversationId}/messages/${messageId}/confirm-action`,
    {
      method: "POST",
      // Only sent for the handful of actions that need it
      // (proposed_action.confirmation_phrase set) — omitted entirely for
      // every normal single-click confirm, matching the backend's own
      // optional body.
      body: confirmationText !== undefined ? JSON.stringify({ confirmation_text: confirmationText }) : undefined,
      // Longer budget than a normal request — this is where a write
      // tool's real work actually runs (see API_CONFIRM_ACTION_TIMEOUT_MS).
      signal: AbortSignal.timeout(API_CONFIRM_ACTION_TIMEOUT_MS),
    },
  );
}

export function cancelAction(conversationId: string, messageId: string): Promise<ChatMessage> {
  return apiFetch<ChatMessage>(
    `/chat/conversations/${conversationId}/messages/${messageId}/cancel-action`,
    { method: "POST" },
  );
}

export interface ChatAttachment {
  url: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export function uploadChatAttachment(file: File): Promise<ChatAttachment> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<ChatAttachment>("/chat/attachments", {
    method: "POST",
    body: formData,
  });
}

/**
 * Same upload as `uploadChatAttachment`, but via `XMLHttpRequest` instead
 * of `fetch` — the Fetch API has no upload-progress event at all, so a
 * real progress bar (and a cancel button that actually stops the bytes
 * mid-transfer, not just the UI pretending to) needs XHR specifically.
 * Returns an object exposing a `promise` to await and a `cancel()` to
 * abort the in-flight request.
 */
export function uploadChatAttachmentWithProgress(
  file: File,
  onProgress: (fractionComplete: number) => void,
): { promise: Promise<ChatAttachment>; cancel: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<ChatAttachment>((resolve, reject) => {
    (async () => {
      const token = await getAccessToken();
      xhr.open("POST", `${API_BASE_URL}${API_V1}/chat/attachments`);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded / event.total);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText) as ChatAttachment);
          } catch {
            reject(new ApiError("Upload response wasn't valid JSON", xhr.status, xhr.responseText));
          }
        } else {
          apiErrorFromResponse(
            new Response(xhr.responseText, { status: xhr.status }),
          ).then(reject);
        }
      };
      xhr.onerror = () => reject(apiErrorFromNetworkFailure(new Error("Upload failed")));
      xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));

      const formData = new FormData();
      formData.append("file", file);
      xhr.send(formData);
    })().catch(reject);
  });

  return { promise, cancel: () => xhr.abort() };
}

/** Streaming send — calls the SSE endpoint and yields events via callbacks. */
export async function sendMessageStream(
  conversationId: string,
  content: string,
  callbacks: {
    onToken: (text: string) => void;
    onTool: (name: string) => void;
    onDone: (message: ChatMessage) => void;
    onError: (text: string) => void;
  },
): Promise<void> {
  const token = await getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  // An *idle*-gap timeout, not a fixed deadline on the whole request:
  // `AbortSignal.timeout()` aborts a fetch — including a readable stream
  // it's already mid-read on — after a fixed absolute duration whether or
  // not new chunks are still arriving. A real turn can run several tool
  // calls (each its own full Claude round trip) before the first token
  // streams, easily past any fixed ceiling under ordinary latency
  // variance — confirmed live via a genuine "BodyStreamBuffer was
  // aborted" abort mid-turn, with the backend's own log showing that
  // exact request cancelled server-side at the same moment. Resetting the
  // timer on every chunk means a stream that's actively doing visible
  // work never times out — only a genuinely stuck one does.
  const controller = new AbortController();
  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  const resetIdleTimer = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => controller.abort(), API_STREAM_IDLE_TIMEOUT_MS);
  };
  resetIdleTimer();

  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}${API_V1}/chat/conversations/${conversationId}/messages/stream`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ content }),
        signal: controller.signal,
      },
    );
  } catch (cause) {
    clearTimeout(idleTimer);
    callbacks.onError(describeError(apiErrorFromNetworkFailure(cause)));
    return;
  }

  if (!response.ok || !response.body) {
    clearTimeout(idleTimer);
    callbacks.onError(describeError(await apiErrorFromResponse(response)));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      resetIdleTimer();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE lines: "data: {...}\n\n"
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data: ")) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === "token") callbacks.onToken(event.text);
          else if (event.type === "tool") callbacks.onTool(event.name);
          else if (event.type === "done") callbacks.onDone(event.message as ChatMessage);
          else if (event.type === "error") callbacks.onError(event.text);
        } catch {
          // malformed chunk — skip
        }
      }
    }
  } catch (cause) {
    callbacks.onError(describeError(apiErrorFromNetworkFailure(cause)));
  } finally {
    clearTimeout(idleTimer);
  }
}

// ---------------------------------------------------------------------------
// Media & Asset Library
// ---------------------------------------------------------------------------

export interface MediaAsset {
  id: string;
  company_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  public_url: string | null;
  tags: string[] | null;
  uploaded_by: string | null;
  created_at: string;
}

export function uploadMediaAsset(
  companyId: string,
  file: File,
  options: { tags?: string; uploadedBy?: string } = {},
): Promise<MediaAsset> {
  const formData = new FormData();
  formData.append("file", file);
  if (options.tags) formData.append("tags", options.tags);
  if (options.uploadedBy) formData.append("uploaded_by", options.uploadedBy);
  return apiFetch<MediaAsset>(`/media-library/${companyId}/assets`, {
    method: "POST",
    body: formData,
  });
}

export function listMediaAssets(
  companyId: string,
  tag?: string,
): Promise<{ items: MediaAsset[] }> {
  return apiFetch<{ items: MediaAsset[] }>(
    `/media-library/${companyId}/assets${toQueryString({ tag })}`,
  );
}

export function deleteMediaAsset(assetId: string): Promise<MediaAsset> {
  return apiFetch<MediaAsset>(`/media-library/assets/${assetId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Analysis — the "5 questions" performance overview, built on real per-post
// metrics (see backend/app/agents/social_media_analyzer/analysis.py). Every
// number here is real; `null` means a platform genuinely doesn't expose that
// metric (e.g. LinkedIn has no comments/shares/views anywhere in Composio's
// current toolkit), never a fabricated zero.
// ---------------------------------------------------------------------------

export interface MetricTotals {
  posts: number;
  reach: number | null;
  engagement: number;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  saves: number | null;
  views: number | null;
}

export interface BreakdownRow {
  key: string;
  posts: number;
  total_engagement: number;
  avg_engagement: number;
}

export interface AnalysisOverview {
  company_id: string;
  period_days: number;
  posts_published: number;
  posts_failed: number;
  current_totals: MetricTotals;
  previous_totals: MetricTotals;
  reach_change_pct: number | null;
  engagement_change_pct: number | null;
  by_platform: BreakdownRow[];
  by_content_type: BreakdownRow[];
  by_topic: BreakdownRow[];
  best_platform: string | null;
  worst_platform: string | null;
  best_content_type: string | null;
  worst_content_type: string | null;
  best_topic: string | null;
  worst_topic: string | null;
  metrics_available: boolean;
  ai_why: string | null;
  ai_recommendations: string[];
}

export function getAnalysisOverview(
  companyId: string,
  periodDays?: number,
): Promise<AnalysisOverview> {
  return apiFetch<AnalysisOverview>(
    `/analysis/overview${toQueryString({ company_id: companyId, period_days: periodDays })}`,
  );
}
