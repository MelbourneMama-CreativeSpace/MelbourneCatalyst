"use client";

import { useEffect, useState } from "react";
import { FileIcon, X } from "lucide-react";

export interface AttachmentMedia {
  url: string;
  filename: string;
  content_type: string;
}

function isImage(contentType: string): boolean {
  return contentType.startsWith("image/");
}

function isVideo(contentType: string): boolean {
  return contentType.startsWith("video/");
}

/**
 * A clickable preview for one attachment — a real thumbnail for images
 * and video (click opens a full-size lightbox), or a generic icon +
 * filename for anything else (a PDF/doc has nothing bigger to "expand"
 * into, so it just opens the raw file in a new tab). Used both in the
 * composer's pending-attachment row and in a sent message bubble, so an
 * attachment looks and behaves the same whether you're about to send it
 * or looking back at it.
 */
export function AttachmentThumbnail({
  media,
  size = "sm",
}: {
  media: AttachmentMedia;
  size?: "sm" | "md";
}) {
  const [expanded, setExpanded] = useState(false);
  const dim = size === "sm" ? "h-8 w-8" : "h-32 w-32";

  if (isImage(media.content_type)) {
    return (
      <>
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className={`${dim} shrink-0 overflow-hidden rounded border border-border/50 transition-opacity hover:opacity-80`}
          aria-label={`Expand ${media.filename}`}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={media.url} alt={media.filename} className="h-full w-full object-cover" />
        </button>
        {expanded && <Lightbox media={media} onClose={() => setExpanded(false)} />}
      </>
    );
  }

  if (isVideo(media.content_type)) {
    return (
      <>
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className={`${dim} group relative shrink-0 overflow-hidden rounded border border-border/50 bg-black`}
          aria-label={`Expand ${media.filename}`}
        >
          {/* preload="metadata" is enough for the browser to paint the
              first frame as a poster without downloading the whole file */}
          <video src={media.url} className="h-full w-full object-cover" muted preload="metadata" />
          <span className="absolute inset-0 flex items-center justify-center bg-black/20 transition-colors group-hover:bg-black/35">
            <svg viewBox="0 0 24 24" className="h-5 w-5 fill-white drop-shadow">
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
        </button>
        {expanded && <Lightbox media={media} onClose={() => setExpanded(false)} />}
      </>
    );
  }

  return (
    <a
      href={media.url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-foreground hover:underline"
    >
      <FileIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      {media.filename}
    </a>
  );
}

function Lightbox({ media, onClose }: { media: AttachmentMedia; onClose: () => void }) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute right-4 top-4 rounded-full bg-black/40 p-2 text-white hover:bg-black/60"
        aria-label="Close"
      >
        <X className="h-5 w-5" />
      </button>
      <div className="max-h-full max-w-full" onClick={(e) => e.stopPropagation()}>
        {isImage(media.content_type) ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={media.url}
            alt={media.filename}
            className="max-h-[85vh] max-w-full rounded-lg object-contain"
          />
        ) : (
          <video
            src={media.url}
            controls
            autoPlay
            className="max-h-[85vh] max-w-full rounded-lg"
          />
        )}
      </div>
    </div>
  );
}
