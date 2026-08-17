import "server-only";

/**
 * Server Component-only mirror of a handful of `api.ts` GET calls —
 * the ones actually called during SSR (`await getX(id)` in a page.tsx).
 * Exists only because `api.ts` is shared with Client Components and
 * therefore can't reference `next/headers`; see the comment on
 * `getAccessToken` there for why that split is necessary rather than
 * one function auto-detecting its environment.
 *
 * Deliberately thin: reuses `api.ts`'s types and `toQueryString` (both
 * erased/pure, no runtime `next/headers` dependency), just swaps in a
 * server-side token source.
 */

import { API_TIMEOUT_MS, apiErrorFromNetworkFailure, apiErrorFromResponse } from "@/lib/api-error";
import { createClient } from "@/lib/supabase/server";
import {
  toQueryString,
  type AnalysisOverview,
  type Campaign,
  type Collaboration,
  type Company,
  type CompanyListResponse,
  type Competitor,
  type ContentPlan,
  type DashboardSummary,
  type KnowledgeAuditReport,
  type ListTrendsParams,
  type SourceStatus,
  type Strategy,
  type TrendListResponse,
  type TrendReport,
} from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_V1 = "/api/v1";

async function serverApiFetch<T>(path: string): Promise<T> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_V1}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(API_TIMEOUT_MS),
    });
  } catch (cause) {
    throw apiErrorFromNetworkFailure(cause);
  }
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  return response.json() as Promise<T>;
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return serverApiFetch<DashboardSummary>("/dashboard/summary");
}

export function getAnalysisOverview(
  companyId: string,
  periodDays?: number,
): Promise<AnalysisOverview> {
  return serverApiFetch<AnalysisOverview>(
    `/analysis/overview${toQueryString({ company_id: companyId, period_days: periodDays })}`,
  );
}

export function listCompanies(): Promise<CompanyListResponse> {
  return serverApiFetch<CompanyListResponse>("/companies/");
}

export function getCompany(id: string): Promise<Company> {
  return serverApiFetch<Company>(`/companies/${id}`);
}

export function getStrategy(id: string): Promise<Strategy> {
  return serverApiFetch<Strategy>(`/content-management/strategies/${id}`);
}

export function getContentPlan(id: string): Promise<ContentPlan> {
  return serverApiFetch<ContentPlan>(`/content-management/content-plans/${id}`);
}

export function getCampaign(id: string): Promise<Campaign> {
  return serverApiFetch<Campaign>(`/content-management/campaigns/${id}`);
}

export function getCollaboration(id: string): Promise<Collaboration> {
  return serverApiFetch<Collaboration>(`/content-management/collaborations/${id}`);
}

export function getCompetitor(id: string): Promise<Competitor> {
  return serverApiFetch<Competitor>(`/competitor-research/competitors/${id}`);
}

export function getAuditReport(id: string): Promise<KnowledgeAuditReport> {
  return serverApiFetch<KnowledgeAuditReport>(`/knowledge-base/audit-reports/${id}`);
}

export function getTrendReport(id: string): Promise<TrendReport> {
  return serverApiFetch<TrendReport>(`/trend-analyzer/reports/${id}`);
}

export function listTrends(params: ListTrendsParams = {}): Promise<TrendListResponse> {
  return serverApiFetch<TrendListResponse>(`/trend-analyzer/${toQueryString({ ...params })}`);
}

export function listRecommendedTrends(
  limit?: number,
  companyId?: string,
): Promise<TrendListResponse> {
  return serverApiFetch<TrendListResponse>(
    `/trend-analyzer/recommended${toQueryString({ limit, company_id: companyId })}`,
  );
}

export function getSourceStatus(): Promise<SourceStatus[]> {
  return serverApiFetch<SourceStatus[]>("/trend-analyzer/sources");
}

export function getTrendsByIds(ids: string[]): Promise<TrendListResponse> {
  if (ids.length === 0) return Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 });
  const query = new URLSearchParams();
  for (const id of ids) query.append("ids", id);
  query.set("limit", String(ids.length));
  return serverApiFetch<TrendListResponse>(`/trend-analyzer/?${query.toString()}`);
}

export function listContentItems(params: {
  companyId?: string;
  platform?: string;
} = {}): Promise<{ items: import("@/lib/api").ContentItemWithCompany[] }> {
  return serverApiFetch<{ items: import("@/lib/api").ContentItemWithCompany[] }>(
    `/content-management/content-items${toQueryString({
      company_id: params.companyId,
      platform: params.platform,
    })}`,
  );
}

export function listPendingApprovals(): Promise<import("@/lib/api").PendingApprovalListResponse> {
  return serverApiFetch<import("@/lib/api").PendingApprovalListResponse>(
    "/content-management/approvals/pending",
  );
}
