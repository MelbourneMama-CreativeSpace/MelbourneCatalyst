"use client";

import { useEffect, useRef, useState } from "react";
import { FileIcon, Trash2, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { describeError } from "@/lib/api-error";
import { deleteMediaAsset, listMediaAssets, uploadMediaAsset, type MediaAsset } from "@/lib/api";

export function MediaLibraryView({ companyId }: { companyId: string }) {
  const [assets, setAssets] = useState<MediaAsset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [tagFilter, setTagFilter] = useState("");
  const [tagsInput, setTagsInput] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tagFilter]);

  function load() {
    listMediaAssets(companyId, tagFilter || undefined)
      .then((res) => setAssets(res.items))
      .catch(() => setError("Couldn't load the media library."));
  }

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadMediaAsset(companyId, file, { tags: tagsInput || undefined });
      setTagsInput("");
      load();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDelete(asset: MediaAsset) {
    try {
      await deleteMediaAsset(asset.id);
      setAssets((prev) => prev?.filter((a) => a.id !== asset.id) ?? null);
    } catch {
      setError("Couldn't delete that file — try again.");
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 py-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Media library</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="Tags for next upload, comma-separated"
            className="flex-1 min-w-[180px] rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring"
          />
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleFileSelected}
            disabled={uploading}
            className="hidden"
          />
          <Button
            size="sm"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            className="gap-1.5"
          >
            <Upload className="h-3.5 w-3.5" />
            {uploading ? "Uploading…" : "Upload"}
          </Button>
        </div>

        <input
          value={tagFilter}
          onChange={(e) => setTagFilter(e.target.value)}
          placeholder="Filter by tag…"
          className="w-full rounded-md border border-input bg-transparent px-2.5 py-1.5 text-xs text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring"
        />

        {error && <p className="text-sm text-destructive">{error}</p>}

        {assets !== null && assets.length === 0 && !error && (
          <p className="text-sm text-muted-foreground">No files uploaded yet.</p>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {assets?.map((asset) => (
            <div key={asset.id} className="group relative rounded-lg border border-border p-2">
              <button
                type="button"
                onClick={() => handleDelete(asset)}
                aria-label="Delete"
                className="absolute right-1.5 top-1.5 rounded-md bg-background/80 p-1 opacity-0 transition-opacity group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5 text-destructive" />
              </button>
              {asset.public_url && asset.content_type.startsWith("image/") ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={asset.public_url}
                  alt={asset.filename}
                  className="h-24 w-full rounded-md object-cover"
                />
              ) : (
                <div className="flex h-24 w-full items-center justify-center rounded-md bg-muted">
                  <FileIcon className="h-8 w-8 text-muted-foreground" />
                </div>
              )}
              <p className="mt-1.5 truncate text-xs font-medium">{asset.filename}</p>
              {asset.tags && asset.tags.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {asset.tags.map((t) => (
                    <Badge key={t} variant="outline" className="text-[10px]">
                      {t}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
