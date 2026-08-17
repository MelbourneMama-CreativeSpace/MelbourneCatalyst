"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { describeError } from "@/lib/api-error";
import {
  createManualContentItem,
  type ContentItem,
  type ContentType,
  type Platform,
} from "@/lib/api";

const PLATFORMS: Platform[] = [
  "instagram",
  "linkedin",
  "twitter",
  "tiktok",
  "youtube",
  "blog",
  "facebook",
  "threads",
];
const CONTENT_TYPES: ContentType[] = [
  "post",
  "video",
  "article",
  "carousel",
  "story",
  "newsletter",
  "podcast",
];

export function ManualDraftForm({ companyId }: { companyId: string }) {
  const [platform, setPlatform] = useState<Platform>("instagram");
  const [contentType, setContentType] = useState<ContentType>("post");
  const [topic, setTopic] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ContentItem | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim()) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const item = await createManualContentItem(companyId, platform, contentType, topic.trim());
      setResult(item);
      setTopic("");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Add a draft manually</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          Give it a topic and a platform — it drafts real, ready-to-publish copy,
          grounded in this company&apos;s brand voice and knowledge base.
        </p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-3">
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value as Platform)}
              className="rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none"
            >
              {PLATFORMS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <select
              value={contentType}
              onChange={(e) => setContentType(e.target.value as ContentType)}
              className="rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none"
            >
              {CONTENT_TYPES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="What should this post be about?"
            rows={2}
            className="resize-none rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <div>
            <Button type="submit" disabled={submitting || !topic.trim()} size="sm">
              {submitting ? "Drafting…" : "Generate draft"}
            </Button>
          </div>
        </form>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {result && (
          <div className="rounded-lg border border-border p-4">
            <p className="text-sm font-medium">{result.title}</p>
            <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
              {result.draft_copy}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
