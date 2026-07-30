import Link from "next/link";
import { notFound } from "next/navigation";

import { CompanyProfile } from "@/components/company-profile";
import { type Company } from "@/lib/api";
import { getCompany } from "@/lib/api-server";

interface CompanyPageProps {
  params: Promise<{ id: string }>;
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

export default async function CompanyPage({ params }: CompanyPageProps) {
  const { id } = await params;
  const company = await fetchCompanyOrNotFound(id);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link href="/companies" className="text-sm text-muted-foreground hover:text-foreground">
          &larr; All companies
        </Link>
        <CompanyProfile initialCompany={company} />
      </div>
    </div>
  );
}
