"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  Send,
  X,
  Mic,
  Paperclip,
  ChevronDown,
  AudioLines,
  Square,
  Wrench,
} from "lucide-react";
import { Streamdown, type Components } from "streamdown";

import { Button } from "@/components/ui/button";
import { AttachmentThumbnail } from "@/components/chat-attachment-media";
import { ChatCards } from "@/components/chat-cards";
import { describeError } from "@/lib/api-error";
import { parseMessageAttachments } from "@/lib/chat-attachments";
import { cn } from "@/lib/utils";
import { useReadAloud, useVoiceInput } from "@/hooks/use-speech";
import {
  cancelAction,
  confirmAction,
  getConversation,
  sendMessageStream,
  uploadChatAttachmentWithProgress,
  type ChatAttachment,
  type ChatMessage,
} from "@/lib/api";

const markdownComponents: Components = {
  h1: ({ className, ...props }) => (
    <h1 className={cn("mt-3 mb-1 text-sm font-semibold text-foreground", className)} {...props} />
  ),
  h2: ({ className, ...props }) => (
    <h2 className={cn("mt-3 mb-1 text-sm font-semibold text-foreground", className)} {...props} />
  ),
  h3: ({ className, ...props }) => (
    <h3 className={cn("mt-2 mb-1 text-sm font-semibold text-foreground", className)} {...props} />
  ),
  h4: ({ className, ...props }) => (
    <h4 className={cn("mt-2 mb-1 text-xs font-semibold text-foreground", className)} {...props} />
  ),
  p: ({ className, ...props }) => (
    <p className={cn("my-1.5 first:mt-0 last:mb-0 leading-relaxed", className)} {...props} />
  ),
  ul: ({ className, ...props }) => (
    <ul className={cn("my-1.5 space-y-0.5", className)} {...props} />
  ),
  ol: ({ className, ...props }) => (
    <ol className={cn("my-1.5 space-y-0.5", className)} {...props} />
  ),
  strong: ({ className, ...props }) => (
    <strong className={cn("font-semibold text-foreground", className)} {...props} />
  ),
};

// ── Streaming bubble: renders tokens as they arrive ───────────────────────

// A natural-language "what I'm doing right now" label per read tool —
// same spirit as Claude.ai's own contextual status text, instead of just
// echoing the raw tool name ("Using create content item…" reads like
// debug output, not something meant for the person waiting on it). Covers
// every read tool that can actually emit a "tool" progress event (write
// tools end the turn as a proposal before ever reaching that point, so
// they never need an entry here); anything unlisted — a future tool this
// map hasn't caught up with yet — falls back to the humanized name so
// nothing breaks, it just reads a little more raw until this map is
// updated.
const TOOL_PROGRESS_LABELS: Record<string, string> = {
  list_companies: "Looking up your companies",
  list_trending_topics: "Checking what's trending",
  get_company_summary: "Pulling up the company profile",
  search_knowledge_base: "Searching your knowledge base",
  get_content_pipeline_status: "Checking the content pipeline",
  find_content_items: "Looking through your content",
  create_content_item: "Writing your post",
  get_youtube_video_analytics: "Fetching YouTube stats",
};

function toolProgressLabel(toolName: string): string {
  return TOOL_PROGRESS_LABELS[toolName] ?? `Using ${toolName.replace(/_/g, " ")}`;
}

function StreamingBubble({
  text,
  toolsInProgress,
}: {
  text: string;
  toolsInProgress: string[];
}) {
  return (
    <div className="flex gap-4 animate-fade-in">
      <div className="shrink-0 flex items-start pt-1">
        <div className="w-8 h-8 rounded-full border border-border/35 bg-card flex items-center justify-center overflow-hidden shadow-sm animate-pulse">
          <Image src="/loomverse-mark.png" alt="LoomVerse AI" width={20} height={20} />
        </div>
      </div>
      <div className="flex-1 min-w-0 pt-1">
        {toolsInProgress.length > 0 && !text && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
            <Wrench className="h-3 w-3 animate-spin-slow" />
            <span>{toolProgressLabel(toolsInProgress[toolsInProgress.length - 1])}…</span>
          </div>
        )}
        {text ? (
          <div className="text-sm leading-relaxed text-foreground">
            <Streamdown mode="static" animated={false} components={markdownComponents}>
              {text}
            </Streamdown>
            {/* Blinking cursor at end */}
            <span className="inline-block w-0.5 h-4 bg-foreground/70 ml-0.5 align-middle animate-blink" />
          </div>
        ) : (
          <div className="flex items-center gap-1 pt-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:0ms]" />
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:150ms]" />
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:300ms]" />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────

export function ChatPanel({
  conversationId,
  initialMessages,
  onActionConfirmed,
  compact = false,
}: {
  conversationId: string;
  initialMessages: ChatMessage[];
  onActionConfirmed?: () => void;
  // For embedding as a slim dock (Content Studio's bottom bar) rather
  // than a full page: skips the big "your AI content team is ready"
  // splash (wasted space when this is just one panel among several, not
  // the whole screen) and lets the transcript area size to its content
  // (capped, then scrolling) instead of always claiming its parent's
  // full height — so an empty/short conversation collapses down to just
  // the composer, reading as a chat bar, and grows only once there's
  // something to show.
  compact?: boolean;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionPendingId, setActionPendingId] = useState<string | null>(null);

  // Streaming state — lives outside messages[] while the stream is live
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [streamingTools, setStreamingTools] = useState<string[]>([]);

  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  // In-flight uploads, separate from `attachments` (which only holds
  // completed ones) — tracks per-file progress and a cancel handle so the
  // composer can show a real progress bar and let an upload be aborted
  // mid-transfer, not just hide a spinner behind a disabled button.
  const [pendingUploads, setPendingUploads] = useState<
    { id: string; filename: string; progress: number; cancel: () => void }[]
  >([]);
  const uploading = pendingUploads.length > 0;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const scrollContentRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  const voiceInput = useVoiceInput((transcript) =>
    setInput((prev) => (prev ? `${prev} ${transcript}` : transcript)),
  );
  const readAloud = useReadAloud();
  const lastAssistantMessage = [...messages].reverse().find((m) => m.role !== "user");
  const readAloudText = input.trim() || lastAssistantMessage?.content || "";

  function scrollToBottom(behavior: ScrollBehavior = "smooth") {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  }

  function handleScroll() {
    const el = scrollContainerRef.current;
    if (!el) return;
    stickToBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }

  useEffect(() => {
    scrollToBottom("auto");
  }, [conversationId]);

  // Scroll as tokens arrive
  useEffect(() => {
    if (stickToBottomRef.current) scrollToBottom("auto");
  }, [streamingText, messages, sending]);

  useEffect(() => {
    const content = scrollContentRef.current;
    if (!content) return;
    const observer = new ResizeObserver(() => {
      if (stickToBottomRef.current) scrollToBottom("auto");
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  // Auto-send a message staged on the splash screen
  useEffect(() => {
    const key = `loomverse:pending-message:${conversationId}`;
    const pending = sessionStorage.getItem(key);
    if (!pending) return;
    sessionStorage.removeItem(key);
    if (messages.length === 0) void handleSend(pending);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setError(null);

    const id = `upload-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const { promise, cancel } = uploadChatAttachmentWithProgress(file, (fraction) => {
      setPendingUploads((prev) =>
        prev.map((u) => (u.id === id ? { ...u, progress: fraction } : u)),
      );
    });
    setPendingUploads((prev) => [...prev, { id, filename: file.name, progress: 0, cancel }]);

    try {
      const attachment = await promise;
      setAttachments((prev) => [...prev, attachment]);
    } catch (err) {
      // A user-initiated cancel isn't an error worth showing — anything
      // else (a real upload failure) is.
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(describeError(err));
      }
    } finally {
      setPendingUploads((prev) => prev.filter((u) => u.id !== id));
    }
  }

  function removeAttachment(url: string) {
    setAttachments((prev) => prev.filter((a) => a.url !== url));
  }

  async function handleSend(overrideContent?: string) {
    const text = (overrideContent ?? input).trim();
    if ((!text && attachments.length === 0) || sending) return;

    setError(null);
    setInput("");

    const attachmentMd = attachments
      .map((a) =>
        a.content_type.startsWith("image/")
          ? `![${a.filename}](${a.url})`
          : `[${a.filename}](${a.url})`,
      )
      .join("\n");
    const content = [text, attachmentMd].filter(Boolean).join("\n\n");

    const sentAttachments = [...attachments];
    setAttachments([]);
    setSending(true);

    // Optimistic user bubble
    const tempUserId = `pending-user-${Date.now()}`;
    const optimisticUser: ChatMessage = {
      id: tempUserId,
      conversation_id: conversationId,
      role: "user",
      content,
      tool_calls_summary: null,
      proposed_action: null,
      action_status: null,
      cards: null,
      ok: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);

    // Start the streaming bubble (empty = dots; fills as tokens arrive)
    setStreamingText("");
    setStreamingTools([]);

    try {
      await sendMessageStream(conversationId, content, {
        onToken: (chunk) => {
          setStreamingText((prev) => (prev ?? "") + chunk);
        },
        onTool: (name) => {
          setStreamingTools((prev) => [...prev, name]);
        },
        onDone: (assistantMessage) => {
          // Replace streaming bubble with the real persisted message
          setStreamingText(null);
          setStreamingTools([]);
          setMessages((prev) => [...prev, assistantMessage]);
          window.dispatchEvent(new Event("loomverse:conversations-updated"));
        },
        onError: (errText) => {
          setStreamingText(null);
          setStreamingTools([]);
          setError(errText);
          setAttachments(sentAttachments);
        },
      });
    } catch (err) {
      setStreamingText(null);
      setStreamingTools([]);
      setError(describeError(err));
      setAttachments(sentAttachments);
    } finally {
      setSending(false);
    }
  }

  async function handleConfirm(message: ChatMessage, confirmationText?: string) {
    setError(null);
    setActionPendingId(message.id);
    try {
      await confirmAction(conversationId, message.id, confirmationText);
      const refreshed = await getConversation(conversationId);
      setMessages(refreshed.messages);
      onActionConfirmed?.();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setActionPendingId(null);
    }
  }

  async function handleCancel(message: ChatMessage) {
    setError(null);
    setActionPendingId(message.id);
    try {
      await cancelAction(conversationId, message.id);
      const refreshed = await getConversation(conversationId);
      setMessages(refreshed.messages);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setActionPendingId(null);
    }
  }

  const hasContent = messages.length > 0 || streamingText !== null;
  // Compact + nothing to show yet: no scroll container at all (not even
  // an empty, padded one) — that's what actually collapses the dock down
  // to just the composer's height. A full-page chat always shows this
  // area (with the splash while empty) since it owns the whole viewport
  // either way.
  const showTranscript = !compact || hasContent;

  return (
    <div className={`flex flex-col bg-background text-foreground ${compact ? "" : "h-full"}`}>
      {showTranscript && (
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className={`overflow-y-auto px-6 py-8 ${compact ? "max-h-[340px]" : "flex-1"}`}
        >
          <div ref={scrollContentRef} className="mx-auto max-w-2xl flex flex-col gap-6">
          {messages.length === 0 && streamingText === null ? (
            compact ? null : (
              <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
                <p className="text-base font-medium text-foreground">Your AI content team is ready.</p>
                <p className="text-sm text-muted-foreground max-w-sm">
                  Ask me to write a post, plan next week&apos;s content, check what&apos;s trending for your clients, or review the pipeline.
                </p>
              </div>
            )
          ) : (
            messages.map((message, index) => (
              <MessageBubble
                key={message.id}
                message={message}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
                actionBusy={actionPendingId === message.id}
                // A pending proposal is only actionable while the
                // conversation hasn't moved past it — once any later
                // message exists (the user replied, a new turn started),
                // re-confirming it could mean acting on something the
                // conversation has since superseded. Mirrors the same
                // "newer message exists" rule the backend now enforces
                // server-side in `_get_pending_action_message`.
                isExpired={
                  message.proposed_action != null &&
                  message.action_status === "pending" &&
                  index !== messages.length - 1
                }
              />
            ))
          )}

          {/* Live streaming bubble — shown while tokens are arriving */}
          {streamingText !== null && (
            <StreamingBubble
              text={streamingText}
              toolsInProgress={streamingTools}
            />
          )}
          </div>
        </div>
      )}

      {error && (
        <div className="mx-auto w-full max-w-2xl px-6 pb-2">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Input area */}
      <div className="px-6 py-4 bg-background border-t border-border/20">
        <div className="mx-auto max-w-2xl bg-card border border-border shadow-sm rounded-2xl p-3 flex flex-col gap-2 focus-within:ring-2 focus-within:ring-ring/25 focus-within:border-border/90 transition-all duration-200">

          {(attachments.length > 0 || pendingUploads.length > 0) && (
            <div className="flex flex-wrap gap-2 pb-1">
              {attachments.map((a) => (
                <div
                  key={a.url}
                  className="group relative flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-2 py-1"
                >
                  <AttachmentThumbnail media={a} />
                  <span className="max-w-[120px] truncate text-xs text-foreground">{a.filename}</span>
                  <button
                    type="button"
                    onClick={() => removeAttachment(a.url)}
                    className="ml-0.5 rounded p-0.5 text-muted-foreground hover:text-destructive"
                    aria-label="Remove attachment"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
              {pendingUploads.map((u) => (
                <div
                  key={u.id}
                  className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-2 py-1"
                >
                  <div className="flex flex-col gap-1">
                    <span className="max-w-[140px] truncate text-xs text-foreground">
                      {u.filename}
                    </span>
                    <div className="h-1 w-24 overflow-hidden rounded-full bg-border">
                      <div
                        className="h-full rounded-full bg-primary transition-[width] duration-150"
                        style={{ width: `${Math.round(u.progress * 100)}%` }}
                      />
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={u.cancel}
                    className="rounded p-0.5 text-muted-foreground hover:text-destructive"
                    aria-label={`Cancel uploading ${u.filename}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Write a post, plan content, ask anything…"
            rows={2}
            disabled={sending}
            className="w-full resize-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/75"
          />

          <div className="flex items-center justify-between border-t border-border/5 pt-2">
            <div className="flex items-center gap-1">
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelected}
                disabled={uploading || sending}
                accept="image/*,video/*,application/pdf,.doc,.docx,.txt,.csv,.xls,.xlsx"
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || sending}
                className={cn(
                  "p-1.5 rounded-lg transition-colors",
                  uploading
                    ? "text-primary animate-pulse cursor-wait"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                )}
                title={uploading ? "Uploading…" : "Attach a file"}
              >
                <Paperclip className="h-4 w-4" />
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled
                className="flex items-center gap-0.5 px-2.5 py-1 text-[10px] font-medium text-muted-foreground/40 rounded-full border border-border/40 cursor-not-allowed"
              >
                <span>Sonnet 5 Medium</span>
                <ChevronDown className="h-2.5 w-2.5" />
              </button>

              <button
                type="button"
                onClick={voiceInput.toggle}
                disabled={!voiceInput.supported}
                className={`p-1.5 rounded-lg transition-colors ${
                  voiceInput.listening
                    ? "text-destructive bg-destructive/10 animate-pulse"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
                title={voiceInput.listening ? "Stop recording" : "Voice input"}
              >
                <Mic className="h-3.5 w-3.5" />
              </button>

              <button
                type="button"
                onClick={() =>
                  readAloud.speaking ? readAloud.stop() : readAloud.speak(readAloudText)
                }
                disabled={!readAloud.supported || (!readAloud.speaking && !readAloudText)}
                className={`p-1.5 rounded-lg transition-colors ${
                  readAloud.speaking
                    ? "text-primary bg-primary/10"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
                title={readAloud.speaking ? "Stop reading" : "Read aloud"}
              >
                {readAloud.speaking ? <Square className="h-3.5 w-3.5" /> : <AudioLines className="h-3.5 w-3.5" />}
              </button>

              <button
                onClick={() => handleSend()}
                disabled={sending || (!input.trim() && attachments.length === 0)}
                className="p-1.5 bg-primary text-primary-foreground rounded-lg hover:opacity-90 disabled:opacity-50 transition-all ml-1"
                title="Send message"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── MessageBubble (persisted messages) ───────────────────────────────────

function MessageBubble({
  message,
  onConfirm,
  onCancel,
  actionBusy,
  isExpired,
}: {
  message: ChatMessage;
  onConfirm: (message: ChatMessage, confirmationText?: string) => void;
  onCancel: (message: ChatMessage) => void;
  actionBusy: boolean;
  isExpired: boolean;
}) {
  const isUser = message.role === "user";
  const isUnavailable = !isUser && message.ok === false;
  // Only used for the handful of write tools severe/irreversible enough
  // to require typing an exact phrase before Confirm even enables — see
  // proposed_action.confirmation_phrase.
  const [typedConfirmation, setTypedConfirmation] = useState("");
  const requiredPhrase = message.proposed_action?.confirmation_phrase ?? null;
  const typedConfirmationMatches = requiredPhrase === null || typedConfirmation === requiredPhrase;

  if (isUser) {
    // Attachments were appended to `content` as literal markdown syntax
    // when sent (see handleSend) — pulled back out here into real
    // thumbnails instead of raw markdown text or a bare filename label.
    // The rest of the message stays plain text, deliberately never
    // markdown-rendered, so nothing the user typed is reinterpreted out
    // from under them.
    const { text, attachments } = parseMessageAttachments(message.content);
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-secondary border border-border/30 px-4 py-2.5 text-sm text-foreground shadow-sm">
          {text && <p className="whitespace-pre-wrap leading-relaxed">{text}</p>}
          {attachments.length > 0 && (
            <div className={cn("flex flex-wrap gap-2", text && "mt-2")}>
              {attachments.map((a) => (
                <AttachmentThumbnail key={a.url} media={a} size="md" />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-4">
      <div className="shrink-0 flex items-start pt-1">
        <div className="w-8 h-8 rounded-full border border-border/35 bg-card flex items-center justify-center overflow-hidden shadow-sm">
          <Image src="/loomverse-mark.png" alt="LoomVerse AI" width={20} height={20} />
        </div>
      </div>

      <div className="flex-1 min-w-0 pt-1">
        {isUnavailable ? (
          <div className="rounded-xl border border-dashed border-destructive/40 bg-destructive/5 p-3">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-destructive">
              <AlertTriangle className="h-3.5 w-3.5" />
              Not available
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">{message.content}</p>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-sm leading-relaxed text-foreground">
              <Streamdown mode="static" animated={false} components={markdownComponents}>
                {message.content}
              </Streamdown>
            </div>
            {message.tool_calls_summary && message.tool_calls_summary.length > 0 && (
              <p className="text-xs text-muted-foreground font-medium">
                Used: {message.tool_calls_summary.join(", ")}
              </p>
            )}
            {message.cards && <ChatCards cards={message.cards} />}
          </div>
        )}

        {message.proposed_action && (
          <div className="mt-3 max-w-md rounded-xl border border-border bg-card p-3 shadow-sm">
            <p className="text-xs font-semibold text-foreground">
              {message.proposed_action.description}
            </p>
            {message.action_status === "pending" && !isExpired ? (
              <div className="mt-2.5 flex flex-col gap-2">
                {requiredPhrase && (
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-medium text-muted-foreground">
                      This can&apos;t be undone. Type <span className="font-mono font-semibold text-destructive">{requiredPhrase}</span> to confirm.
                    </label>
                    <input
                      type="text"
                      value={typedConfirmation}
                      onChange={(e) => setTypedConfirmation(e.target.value)}
                      placeholder={requiredPhrase}
                      className="rounded-md border border-input bg-transparent px-2 py-1 text-xs font-mono outline-none focus:border-destructive/60"
                    />
                  </div>
                )}
                <div className="flex gap-2">
                  <Button
                    size="xs"
                    onClick={() => onConfirm(message, requiredPhrase ? typedConfirmation : undefined)}
                    disabled={actionBusy || !typedConfirmationMatches}
                    className={cn(
                      "gap-1",
                      requiredPhrase
                        ? "bg-destructive text-destructive-foreground hover:opacity-90"
                        : "bg-primary text-primary-foreground hover:opacity-90",
                    )}
                  >
                    <Check className="h-3 w-3" /> Confirm
                  </Button>
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={() => onCancel(message)}
                    disabled={actionBusy}
                    className="gap-1"
                  >
                    <X className="h-3 w-3" /> Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <p className="mt-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {isExpired ? "Expired" : message.action_status}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
