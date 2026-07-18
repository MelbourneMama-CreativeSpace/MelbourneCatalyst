import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Collaboration, CollaborationIdea, CollaborationPriority } from "@/lib/api";

const PRIORITY_ORDER: Record<CollaborationPriority, number> = { high: 0, medium: 1, low: 2 };

export function CollaborationView({ collaboration }: { collaboration: Collaboration }) {
  const statusVariant = collaboration.status === "complete" ? "default" : "outline";
  const sortedIdeas = [...collaboration.ideas].sort(
    (a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority],
  );

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Collaboration ideas</h1>
        <Badge variant={statusVariant}>{collaboration.status}</Badge>
      </div>

      {collaboration.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Collaboration generation failed
              {collaboration.status_error ? `: ${collaboration.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {collaboration.status !== "failed" && sortedIdeas.length === 0 && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              {collaboration.status === "complete"
                ? "No collaboration ideas were generated."
                : "Generating collaboration ideas…"}
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        {sortedIdeas.map((idea) => (
          <CollaborationIdeaCard key={idea.id} idea={idea} />
        ))}
      </div>
    </div>
  );
}

function CollaborationIdeaCard({ idea }: { idea: CollaborationIdea }) {
  const priorityVariant = idea.priority === "high" ? "default" : "outline";
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{idea.collaborator_archetype}</CardTitle>
          <Badge variant={priorityVariant}>{idea.priority} priority</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm leading-relaxed">{idea.partnership_angle}</p>
        <div>
          <p className="text-xs font-medium text-muted-foreground">Outreach template</p>
          <p className="mt-1 text-sm leading-relaxed whitespace-pre-line">
            {idea.outreach_template}
          </p>
        </div>
        {idea.rationale && (
          <p className="text-xs text-muted-foreground">Why: {idea.rationale}</p>
        )}
      </CardContent>
    </Card>
  );
}
