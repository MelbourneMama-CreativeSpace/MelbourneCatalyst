import Link from "next/link";
import { notFound } from "next/navigation";

import { CollaborationView } from "@/components/collaboration-view";
import { type Collaboration } from "@/lib/api";
import { getCollaboration } from "@/lib/api-server";

interface CollaborationPageProps {
  params: Promise<{ id: string }>;
}

async function fetchCollaborationOrNotFound(id: string): Promise<Collaboration> {
  try {
    return await getCollaboration(id);
  } catch (err) {
    if (err instanceof Error && err.message.includes("404")) {
      notFound();
    }
    throw err;
  }
}

export default async function CollaborationPage({ params }: CollaborationPageProps) {
  const { id } = await params;
  const collaboration = await fetchCollaborationOrNotFound(id);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/companies/${collaboration.company_id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to company
        </Link>
        <CollaborationView collaboration={collaboration} />
      </div>
    </div>
  );
}
