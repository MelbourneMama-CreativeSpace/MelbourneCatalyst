import type { AttachmentMedia } from "@/components/chat-attachment-media";

// Matches the exact markdown syntax handleSend() in chat-panel.tsx appends
// for an attachment: `![filename](url)` for images, `[filename](url)`
// for everything else.
const ATTACHMENT_PATTERN = /!?\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "avif"]);
const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "webm", "avi", "mkv", "m4v"]);

function guessContentType(filename: string, isImageSyntax: boolean): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (isImageSyntax || IMAGE_EXTENSIONS.has(ext)) return "image/*";
  if (VIDEO_EXTENSIONS.has(ext)) return "video/*";
  return "application/octet-stream";
}

/**
 * Splits a sent message's raw content — human-typed text with
 * attachment(s) appended as literal markdown syntax, see `handleSend` —
 * into the plain text and a list of structured attachments, so a sent
 * message can render each one as a real thumbnail instead of raw
 * markdown syntax or a bare "📎 filename" label.
 *
 * The markdown syntax itself only distinguishes "image" (`![...]`) from
 * "everything else" (`[...]`) — not video specifically — so video
 * detection falls back to the filename's extension. Good enough for
 * routing to the right thumbnail type; the original upload's exact
 * `content_type` isn't recoverable from the message text alone.
 */
export function parseMessageAttachments(content: string): {
  text: string;
  attachments: AttachmentMedia[];
} {
  const attachments: AttachmentMedia[] = [];
  const text = content
    .replace(ATTACHMENT_PATTERN, (match, filename: string, url: string) => {
      attachments.push({
        url,
        filename,
        content_type: guessContentType(filename, match.startsWith("!")),
      });
      return "";
    })
    .trim();
  return { text, attachments };
}
