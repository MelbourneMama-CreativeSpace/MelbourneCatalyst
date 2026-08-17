"use client";

import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { describeError } from "@/lib/api-error";
import {
  createManualDocument,
  deleteDocument,
  getKnowledgeFreshness,
  indexBlogFeeds,
  listDocuments,
  searchKnowledgeBase,
  uploadDocument,
  type KnowledgeDocument,
  type KnowledgeFreshness,
  type SearchHit,
} from "@/lib/api";

const SOURCE_TYPE_FILTERS: { label: string; value: string | null }[] = [
  { label: "All", value: null },
  { label: "Website", value: "website" },
  { label: "Product pages", value: "product_page" },
  { label: "Blog", value: "blog" },
  { label: "Uploads", value: "doc_upload" },
  { label: "Manual", value: "manual" },
];

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function KnowledgeBaseDashboard({ companyId }: { companyId: string }) {
  const [freshness, setFreshness] = useState<KnowledgeFreshness | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [manualTitle, setManualTitle] = useState("");
  const [manualContent, setManualContent] = useState("");
  const [savingManual, setSavingManual] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [feedUrlsText, setFeedUrlsText] = useState("");
  const [indexingBlog, setIndexingBlog] = useState(false);
  const [blogIndexError, setBlogIndexError] = useState<string | null>(null);
  const [blogIndexResult, setBlogIndexResult] = useState<string | null>(null);

  function refreshDocuments() {
    listDocuments(companyId, { sourceType: sourceTypeFilter ?? undefined })
      .then(({ items, total }) => {
        setDocuments(items);
        setTotal(total);
        setListError(null);
      })
      .catch((err) => setListError(describeError(err)));
  }

  useEffect(() => {
    getKnowledgeFreshness(companyId).then(setFreshness).catch(() => {});
  }, [companyId]);

  useEffect(() => {
    refreshDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, sourceTypeFilter]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const { hits } = await searchKnowledgeBase(searchQuery, { company_id: companyId, k: 10 });
      setSearchHits(hits);
    } catch (err) {
      setSearchError(describeError(err));
    } finally {
      setSearching(false);
    }
  }

  async function handleDelete(documentId: string) {
    try {
      await deleteDocument(documentId);
      setDocuments((prev) => prev.filter((doc) => doc.id !== documentId));
      setTotal((prev) => prev - 1);
    } catch (err) {
      setListError(describeError(err));
    }
  }

  async function handleManualSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSavingManual(true);
    setManualError(null);
    try {
      await createManualDocument(companyId, manualTitle, manualContent);
      setManualTitle("");
      setManualContent("");
      refreshDocuments();
    } catch (err) {
      setManualError(describeError(err));
    } finally {
      setSavingManual(false);
    }
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      await uploadDocument(companyId, file);
      if (fileInputRef.current) fileInputRef.current.value = "";
      refreshDocuments();
    } catch (err) {
      setUploadError(describeError(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleBlogIndex(e: React.FormEvent) {
    e.preventDefault();
    const feedUrls = feedUrlsText
      .split(/[\n,]/)
      .map((url) => url.trim())
      .filter(Boolean);
    if (feedUrls.length === 0) return;
    setIndexingBlog(true);
    setBlogIndexError(null);
    setBlogIndexResult(null);
    try {
      const result = await indexBlogFeeds(companyId, feedUrls);
      setBlogIndexResult(
        `Indexed ${result.sources_processed} article${result.sources_processed === 1 ? "" : "s"}, ${result.chunks_persisted} chunk${result.chunks_persisted === 1 ? "" : "s"} saved.`,
      );
      refreshDocuments();
    } catch (err) {
      setBlogIndexError(describeError(err));
    } finally {
      setIndexingBlog(false);
    }
  }

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Knowledge base</h1>
        {freshness && (
          <Badge variant="outline">
            {freshness.document_count} {freshness.document_count === 1 ? "document" : "documents"}
            {freshness.staleness_days !== null &&
              ` · updated ${freshness.staleness_days === 0 ? "today" : `${freshness.staleness_days}d ago`}`}
          </Badge>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-muted-foreground">Search</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search this company's knowledge base…"
            />
            <Button type="submit" disabled={searching}>
              {searching ? "Searching…" : "Search"}
            </Button>
          </form>
          {searchError && <p className="text-sm text-destructive">{searchError}</p>}
          {searchHits && (
            <ul className="flex flex-col gap-2">
              {searchHits.length === 0 && (
                <li className="text-sm text-muted-foreground">No matches found.</li>
              )}
              {searchHits.map((hit) => (
                <li key={hit.document_id} className="rounded-md border border-border p-2 text-sm">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <Badge variant="outline">{hit.source_type}</Badge>
                    <span className="text-xs text-muted-foreground">
                      similarity {hit.similarity.toFixed(2)}
                    </span>
                  </div>
                  <p className="line-clamp-3 text-muted-foreground">{hit.content}</p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Add manual entry</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleManualSubmit} className="flex flex-col gap-2">
              <Input
                value={manualTitle}
                onChange={(e) => setManualTitle(e.target.value)}
                placeholder="Title"
                required
              />
              <textarea
                value={manualContent}
                onChange={(e) => setManualContent(e.target.value)}
                placeholder="Content"
                required
                rows={4}
                className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              <Button type="submit" size="sm" disabled={savingManual}>
                {savingManual ? "Saving…" : "Save entry"}
              </Button>
              {manualError && <p className="text-sm text-destructive">{manualError}</p>}
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Upload document</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleUpload} className="flex flex-col gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt,.md"
                required
                className="text-sm file:mr-2 file:rounded-lg file:border-0 file:bg-muted file:px-2 file:py-1 file:text-sm"
              />
              <p className="text-xs text-muted-foreground">PDF, DOCX, TXT, or MD.</p>
              <Button type="submit" size="sm" disabled={uploading}>
                {uploading ? "Uploading…" : "Upload"}
              </Button>
              {uploadError && <p className="text-sm text-destructive">{uploadError}</p>}
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Index blog feeds</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleBlogIndex} className="flex flex-col gap-2">
              <textarea
                value={feedUrlsText}
                onChange={(e) => setFeedUrlsText(e.target.value)}
                placeholder={"One RSS feed URL per line"}
                required
                rows={4}
                className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              <Button type="submit" size="sm" disabled={indexingBlog}>
                {indexingBlog ? "Indexing…" : "Index feeds"}
              </Button>
              {blogIndexError && <p className="text-sm text-destructive">{blogIndexError}</p>}
              {blogIndexResult && <p className="text-sm text-muted-foreground">{blogIndexResult}</p>}
            </form>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-muted-foreground">Documents ({total})</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-1">
            {SOURCE_TYPE_FILTERS.map((filter) => (
              <Button
                key={filter.label}
                type="button"
                size="sm"
                variant={sourceTypeFilter === filter.value ? "default" : "outline"}
                onClick={() => setSourceTypeFilter(filter.value)}
              >
                {filter.label}
              </Button>
            ))}
          </div>

          {listError && <p className="text-sm text-destructive">{listError}</p>}

          {documents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No documents in this view yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {documents.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-start justify-between gap-3 rounded-md border border-border p-2 text-sm"
                >
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{doc.source_type}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(doc.created_at)}
                      </span>
                    </div>
                    <p className="truncate text-xs text-muted-foreground">{doc.source_url}</p>
                    <p className="mt-1 line-clamp-2 text-muted-foreground">{doc.content_preview}</p>
                  </div>
                  <Button variant="destructive" size="sm" onClick={() => handleDelete(doc.id)}>
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
