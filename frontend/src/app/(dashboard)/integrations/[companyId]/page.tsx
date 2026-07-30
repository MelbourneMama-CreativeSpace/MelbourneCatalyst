import Link from "next/link";
import { notFound } from "next/navigation";

import { IntegrationsView } from "@/components/integrations-view";
import { type Company } from "@/lib/api";
import { getCompany } from "@/lib/api-server";

interface IntegrationsPageProps {
  params: Promise<{ companyId: string }>;
  searchParams: Promise<{ connect_error?: string }>;
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

export default async function IntegrationsPage({ params, searchParams }: IntegrationsPageProps) {
  const { companyId } = await params;
  const { connect_error: connectError } = await searchParams;
  const company = await fetchCompanyOrNotFound(companyId);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-6 py-12">
        <Link
          href={`/companies/${companyId}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to {company.name ?? company.url}
        </Link>
        <h1 className="mt-2 mb-1 text-3xl font-bold">Social connections</h1>
        <p className="mb-6 text-sm text-muted-foreground">
          Connect {company.name ?? "this client"}&apos;s accounts to pull in performance data as
          it becomes available. Connecting doesn&apos;t require anything else from Content
          Studio — it&apos;s independent of the strategy and content calendar.
        </p>
        <IntegrationsView companyId={companyId} connectError={connectError} />
      </div>
    </div>
  );
}
