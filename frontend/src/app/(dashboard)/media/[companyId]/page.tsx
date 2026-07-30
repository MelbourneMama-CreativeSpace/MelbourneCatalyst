import Link from "next/link";
import { notFound } from "next/navigation";

import { MediaLibraryView } from "@/components/media-library-view";
import { type Company } from "@/lib/api";
import { getCompany } from "@/lib/api-server";

interface MediaLibraryPageProps {
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

export default async function MediaLibraryPage({ params }: MediaLibraryPageProps) {
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
        <h1 className="mt-3 text-2xl font-bold">Media & asset library</h1>
        <p className="mt-1 text-muted-foreground">
          Images and files for {company.name ?? "this company"}&apos;s content.
        </p>
        <div className="mt-6">
          <MediaLibraryView companyId={company.id} />
        </div>
      </div>
    </div>
  );
}
