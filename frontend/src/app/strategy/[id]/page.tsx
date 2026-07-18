import Link from "next/link";
import { notFound } from "next/navigation";

import { StrategyView } from "@/components/strategy-view";
import { getStrategy, type Strategy } from "@/lib/api";

interface StrategyPageProps {
  params: Promise<{ id: string }>;
}

async function fetchStrategyOrNotFound(id: string): Promise<Strategy> {
  try {
    return await getStrategy(id);
  } catch (err) {
    if (err instanceof Error && err.message.includes("404")) {
      notFound();
    }
    throw err;
  }
}

export default async function StrategyPage({ params }: StrategyPageProps) {
  const { id } = await params;
  const strategy = await fetchStrategyOrNotFound(id);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/companies/${strategy.company_id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to company
        </Link>
        <StrategyView initialStrategy={strategy} />
      </div>
    </div>
  );
}
