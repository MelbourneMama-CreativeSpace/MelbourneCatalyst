import Link from "next/link";
import { notFound } from "next/navigation";

import { KnowledgeAuditView } from "@/components/knowledge-audit-view";
import { ApiError } from "@/lib/api-error";
import { type KnowledgeAuditReport } from "@/lib/api";
import { getAuditReport } from "@/lib/api-server";

interface KnowledgeAuditPageProps {
  params: Promise<{ id: string }>;
}

async function fetchAuditReportOrNotFound(id: string): Promise<KnowledgeAuditReport> {
  try {
    return await getAuditReport(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }
}

export default async function KnowledgeAuditPage({ params }: KnowledgeAuditPageProps) {
  const { id } = await params;
  const report = await fetchAuditReportOrNotFound(id);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/companies/${report.company_id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to company
        </Link>
        <KnowledgeAuditView initialReport={report} />
      </div>
    </div>
  );
}
