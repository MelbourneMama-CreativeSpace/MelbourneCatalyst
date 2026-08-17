import Link from "next/link";
import { notFound } from "next/navigation";

import { CampaignView } from "@/components/campaign-view";
import { ApiError } from "@/lib/api-error";
import { type Campaign } from "@/lib/api";
import { getCampaign } from "@/lib/api-server";

interface CampaignPageProps {
  params: Promise<{ id: string }>;
}

async function fetchCampaignOrNotFound(id: string): Promise<Campaign> {
  try {
    return await getCampaign(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }
}

export default async function CampaignPage({ params }: CampaignPageProps) {
  const { id } = await params;
  const campaign = await fetchCampaignOrNotFound(id);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/companies/${campaign.company_id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to company
        </Link>
        <CampaignView initialCampaign={campaign} />
      </div>
    </div>
  );
}
