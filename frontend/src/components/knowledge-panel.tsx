"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createAuditReport,
  getKnowledgeFreshness,
  listAuditReports,
  type KnowledgeAuditReport,
  type KnowledgeFreshness,
} from "@/lib/api";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function KnowledgePanel({ companyId }: { companyId: string }) {
  const [freshness, setFreshness] = useState<KnowledgeFreshness | null>(null);
  const [reports, setReports] = useState<KnowledgeAuditReport[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    getKnowledgeFreshness(companyId)
      .then(setFreshness)
      .catch(() => {});
    listAuditReports(companyId)
      .then(({ items }) => setReports(items))
      .catch(() => {});
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      await createAuditReport(companyId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate audit report.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">Knowledge base</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {freshness && (
          <p className="text-sm text-muted-foreground">
            {freshness.document_count} {freshness.document_count === 1 ? "document" : "documents"}
            {freshness.staleness_days !== null && (
              <> · last updated {freshness.staleness_days === 0 ? "today" : `${freshness.staleness_days} days ago`}</>
            )}
          </p>
        )}

        {reports.length > 0 && (
          <ul className="flex flex-col gap-2">
            {reports.map((report) => (
              <li key={report.id}>
                <Link
                  href={`/knowledge-audit/${report.id}`}
                  className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                >
                  <span className="truncate text-muted-foreground">
                    {formatDateTime(report.created_at)}
                  </span>
                  <Badge variant={report.status === "complete" ? "default" : "outline"}>
                    {report.status}
                  </Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap gap-3">
          <Button onClick={handleGenerate} disabled={generating}>
            {generating ? "Generating…" : "Generate audit report"}
          </Button>
          <Button
            variant="outline"
            render={<Link href={`/knowledge-base/${companyId}`}>Browse knowledge base</Link>}
            nativeButton={false}
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
