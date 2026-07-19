"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAuditReport, type KnowledgeAuditReport } from "@/lib/api";

const TERMINAL_STATUSES: ReadonlySet<KnowledgeAuditReport["status"]> = new Set([
  "complete",
  "failed",
]);

export function KnowledgeAuditView({
  initialReport,
}: {
  initialReport: KnowledgeAuditReport;
}) {
  const [report, setReport] = useState(initialReport);

  useEffect(() => {
    if (TERMINAL_STATUSES.has(report.status)) return;
    const timer = setInterval(async () => {
      try {
        const fresh = await getAuditReport(report.id);
        setReport(fresh);
        if (TERMINAL_STATUSES.has(fresh.status)) clearInterval(timer);
      } catch {
        // Transient network errors are fine — the next tick retries.
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [report.id, report.status]);

  const statusVariant = report.status === "complete" ? "default" : "outline";

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Knowledge base audit</h1>
        <div className="flex items-center gap-2">
          <Badge variant="outline">{report.document_count_at_generation} documents</Badge>
          <Badge variant={statusVariant}>{report.status}</Badge>
        </div>
      </div>

      {report.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Audit generation failed{report.status_error ? `: ${report.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {!TERMINAL_STATUSES.has(report.status) && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Generating audit…</p>
          </CardContent>
        </Card>
      )}

      <ReportField label="Coverage" value={report.coverage_summary} />
      <ReportField label="Identified gaps" value={report.identified_gaps} />
      <ReportField label="Recommendations" value={report.recommendations} />
    </div>
  );
}

function ReportField({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-relaxed whitespace-pre-line">{value}</p>
      </CardContent>
    </Card>
  );
}
