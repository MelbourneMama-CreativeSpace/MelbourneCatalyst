"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { describeError } from "@/lib/api-error";
import {
  createCompetitor,
  listCompetitors,
  suggestCompetitorNames,
  type CompanyStatus,
  type Competitor,
} from "@/lib/api";

function statusVariant(status: CompanyStatus): "default" | "outline" {
  return status === "complete" ? "default" : "outline";
}

export function CompetitorList({ companyId }: { companyId: string }) {
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[] | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);

  function refresh() {
    listCompetitors(companyId)
      .then(({ items }) => setCompetitors(items))
      .catch(() => {});
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function handleAddCompetitor(event: React.FormEvent) {
    event.preventDefault();
    setAddError(null);
    setSubmitting(true);
    try {
      const trimmed = url.trim();
      const normalized = trimmed.startsWith("http") ? trimmed : `https://${trimmed}`;
      await createCompetitor(companyId, normalized);
      setUrl("");
      refresh();
    } catch (err) {
      setAddError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSuggest() {
    setSuggesting(true);
    setSuggestError(null);
    try {
      const { suggestions: names, ok } = await suggestCompetitorNames(companyId);
      if (!ok) {
        setSuggestError("Couldn't get suggestions right now (check ANTHROPIC_API_KEY).");
      }
      setSuggestions(names);
    } catch (err) {
      setSuggestError(describeError(err));
    } finally {
      setSuggesting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">Competitors</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {competitors.length > 0 && (
          <ul className="flex flex-col gap-2">
            {competitors.map((competitor) => (
              <li key={competitor.id}>
                <Link
                  href={`/competitor/${competitor.id}`}
                  className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                >
                  <span className="truncate">{competitor.name ?? competitor.url}</span>
                  <Badge variant={statusVariant(competitor.status)}>{competitor.status}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={handleAddCompetitor} className="flex flex-wrap gap-2">
          <Input
            type="text"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="competitor-website.com"
            disabled={submitting}
            required
            className="min-w-[200px] flex-1"
          />
          <Button type="submit" disabled={submitting || !url.trim()}>
            {submitting ? "Adding…" : "Add competitor"}
          </Button>
        </form>
        {addError && <p className="text-sm text-destructive">{addError}</p>}

        <div className="flex flex-col gap-2 border-t border-border pt-4">
          <Button variant="outline" size="sm" onClick={handleSuggest} disabled={suggesting}>
            {suggesting ? "Asking Claude…" : "Suggest competitors"}
          </Button>
          {suggestions !== null && suggestions.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="text-xs text-muted-foreground">
                Claude&apos;s guesses from training knowledge — not a live search, so verify
                these are still real and find their URL yourself before adding.
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestions.map((name) => (
                  <Badge key={name} variant="outline">
                    {name}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {suggestions !== null && suggestions.length === 0 && !suggestError && (
            <p className="text-xs text-muted-foreground">No suggestions came back.</p>
          )}
          {suggestError && <p className="text-sm text-destructive">{suggestError}</p>}
        </div>
      </CardContent>
    </Card>
  );
}
