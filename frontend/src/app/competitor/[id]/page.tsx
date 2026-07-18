import Link from "next/link";
import { notFound } from "next/navigation";

import { CompetitorView } from "@/components/competitor-view";
import { getCompetitor, type Competitor } from "@/lib/api";

interface CompetitorPageProps {
  params: Promise<{ id: string }>;
}

async function fetchCompetitorOrNotFound(id: string): Promise<Competitor> {
  try {
    return await getCompetitor(id);
  } catch (err) {
    if (err instanceof Error && err.message.includes("404")) {
      notFound();
    }
    throw err;
  }
}

export default async function CompetitorPage({ params }: CompetitorPageProps) {
  const { id } = await params;
  const competitor = await fetchCompetitorOrNotFound(id);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/companies/${competitor.company_id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to company
        </Link>
        <CompetitorView initialCompetitor={competitor} />
      </div>
    </div>
  );
}
