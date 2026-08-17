import Link from "next/link";
import { notFound } from "next/navigation";

import { TrendReportView } from "@/components/trend-report-view";
import { ApiError } from "@/lib/api-error";
import { type TrendReport } from "@/lib/api";
import { getTrendReport } from "@/lib/api-server";

interface TrendReportPageProps {
  params: Promise<{ id: string }>;
}

async function fetchTrendReportOrNotFound(id: string): Promise<TrendReport> {
  try {
    return await getTrendReport(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }
}

export default async function TrendReportPage({ params }: TrendReportPageProps) {
  const { id } = await params;
  const report = await fetchTrendReportOrNotFound(id);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/companies/${report.company_id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to company
        </Link>
        <TrendReportView initialReport={report} />
      </div>
    </div>
  );
}
