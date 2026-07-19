import Link from "next/link";
import { notFound } from "next/navigation";

import { KnowledgeBaseDashboard } from "@/components/knowledge-base-dashboard";
import { getCompany, type Company } from "@/lib/api";

interface KnowledgeBasePageProps {
  params: Promise<{ companyId: string }>;
}

async function fetchCompanyOrNotFound(id: string): Promise<Company> {
  try {
    return await getCompany(id);
  } catch (err) {
    if (err instanceof Error && err.message.includes("404")) {
      notFound();
    }
    throw err;
  }
}

export default async function KnowledgeBasePage({ params }: KnowledgeBasePageProps) {
  const { companyId } = await params;
  const company = await fetchCompanyOrNotFound(companyId);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/companies/${company.id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to {company.name ?? "company"}
        </Link>
        <KnowledgeBaseDashboard companyId={company.id} />
      </div>
    </div>
  );
}
