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
  FileIcon,
} from "lucide-react";
import { Streamdown, type Components } from "streamdown";

import { Button } from "@/components/ui/button";
import { ChatCards } from "@/components/chat-cards";
import { cn } from "@/lib/utils";
import { useReadAloud, useVoiceInput } from "@/hooks/use-speech";
import {
  cancelAction,
  confirmAction,
  getConversation,
  sendMessage,
  uploadChatAttachment,
  type ChatAttachment,
  type ChatMessage,
} from "@/lib/api";

// Assistant replies come back from the API as complete markdown, not a
// token stream — so `animated` below only staggers the initial reveal of
// each new reply, it doesn't grow the text mid-request.
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
  h5: ({ className, ...props }) => (
    <h5 className={cn("mt-2 mb-1 text-xs font-semibold text-foreground", className)} {...props} />
  ),
  h6: ({ className, ...props }) => (
    <h6 className={cn("mt-2 mb-1 text-xs font-semibold text-foreground", className)} {...props} />
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

export function ChatPanel({
  conversationId,
  initialMessages,
  onActionConfirmed,
}: {
  conversationId: string;
  initialMessages: ChatMessage[];
  // Fired after a proposed write action (approve/reject/regenerate/create
  // a plan or post) is actually confirmed and run — a host page that also
  // shows content items in some other view (e.g. a table) can use this to
  // refetch, since a chat-driven create/approve doesn't otherwise tell
  // anything outside this panel that it happened.
  onActionConfirmed?: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionPendingId, setActionPendingId] = useState<string | null>(null);
  const nextTempId = useRef(0);
  const [animatingId, setAnimatingId] = useState<string | null>(null);

  // Attachment state
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll: stays pinned to the bottom as new content comes in, but
  // backs off the instant the user scrolls up to read earlier messages,
  // so it never yanks them back down mid-read.
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
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom < 120;
  }

  useEffect(() => {
    // Jump straight to the bottom when a conversation is first opened —
    // no need to animate past history that was already there.
    scrollToBottom("auto");
  }, [conversationId]);

  useEffect(() => {
    if (stickToBottomRef.current) scrollToBottom();
  }, [messages, sending]);

  useEffect(() => {
    const content = scrollContentRef.current;
    if (!content) return;
    // Streamdown's word-stagger reveal doesn't grow the layout (the text
    // is laid out immediately; only opacity animates in), but this keeps
    // the view pinned to the bottom for anything that does change height
    // — attachments, wrapped lines, images loading in.
    const observer = new ResizeObserver(() => {
      if (stickToBottomRef.current) scrollToBottom("auto");
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    // A message typed on the splash screen is staged here (not sent
    // directly) so its reply gets the exact same animated
    // send/scroll/loading treatment as every later message, instead of
    // arriving on this page already resolved.
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
    setUploading(true);
    setError(null);
    try {
      const attachment = await uploadChatAttachment(file);
      setAttachments((prev) => [...prev, attachment]);
    } catch (err) {
      setError(
        err instanceof Error && err.message.includes("409")
          ? "Media storage isn't configured — set SUPABASE_SERVICE_ROLE_KEY on the backend."
          : "Couldn't upload that file — try again.",
      );
    } finally {
      setUploading(false);
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

    // Build message content: text + attachment markdown references so the
    // AI agent can see the URLs and filenames.
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

    const optimisticId = `pending-${nextTempId.current++}`;
    const optimisticMessage: ChatMessage = {
      id: optimisticId,
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
    setMessages((prev) => [...prev, optimisticMessage]);

    try {
      const assistantMessage = await sendMessage(conversationId, content);
      setMessages((prev) => [...prev, assistantMessage]);
      setAnimatingId(assistantMessage.id);
      // The backend may have just renamed this conversation from the raw
      // first message to something reflecting its actual intent — tell
      // the sidebar to refetch instead of waiting for the next route
      // change to notice.
      window.dispatchEvent(new Event("loomverse:conversations-updated"));
    } catch {
      setError("Couldn't send that — try again.");
      // Restore attachments so user can retry
      setAttachments(sentAttachments);
    } finally {
      setSending(false);
    }
  }

  async function handleConfirm(message: ChatMessage) {
    setError(null);
    setActionPendingId(message.id);
    try {
      await confirmAction(conversationId, message.id);
      const refreshed = await getConversation(conversationId);
      setMessages(refreshed.messages);
      onActionConfirmed?.();
    } catch {
      setError("Couldn't run that action — try again.");
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
    } catch {
      setError("Couldn't cancel that action — try again.");
    } finally {
      setActionPendingId(null);
    }
  }

  return (
    <div className="flex h-full flex-col bg-background text-foreground transition-colors duration-300">
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-6 py-8"
      >
        <div ref={scrollContentRef} className="mx-auto max-w-2xl flex flex-col gap-6">
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">
              Ask a question about your companies, trends, or content pipeline.
            </p>
          ) : (
            messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
                actionBusy={actionPendingId === message.id}
                animate={message.id === animatingId}
              />
            ))
          )}
          {sending && <ThinkingIndicator />}
        </div>
      </div>

      {error && (
        <div className="mx-auto w-full max-w-2xl px-6 pb-2">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Floating-style input area */}
      <div className="px-6 py-4 bg-background border-t border-border/20">
        <div className="mx-auto max-w-2xl bg-card border border-border shadow-sm rounded-2xl p-3 flex flex-col gap-2 focus-within:ring-2 focus-within:ring-ring/25 focus-within:border-border/90 transition-all duration-200">

          {/* Attachment previews */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 pb-1">
              {attachments.map((a) => (
                <div
                  key={a.url}
                  className="group relative flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-2 py-1"
                >
                  {a.content_type.startsWith("image/") ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={a.url}
                      alt={a.filename}
                      className="h-8 w-8 rounded object-cover"
                    />
                  ) : (
                    <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className="max-w-[120px] truncate text-xs text-foreground">
                    {a.filename}
                  </span>
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
            placeholder="Reply to LoomVerse AI..."
            rows={2}
            disabled={sending}
            className="w-full resize-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/75"
          />

          <div className="flex items-center justify-between border-t border-border/5 pt-2">
            {/* Bottom left actions */}
            <div className="flex items-center gap-1">
              {/* Hidden file input */}
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
                  (uploading || sending) && "disabled:opacity-40 disabled:cursor-not-allowed",
                )}
                title={uploading ? "Uploading…" : "Attach a file"}
              >
                <Paperclip className="h-4 w-4" />
              </button>
            </div>

            {/* Bottom right actions */}
            <div className="flex items-center gap-2">
              {/* Model selection pill */}
              <button
                type="button"
                disabled
                className="flex items-center gap-0.5 px-2.5 py-1 text-[10px] font-medium text-muted-foreground/40 rounded-full border border-border/40 cursor-not-allowed"
                title="Model switching isn't available yet"
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
                    ? "text-destructive bg-destructive/10 animate-pulse-glow"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
                title={
                  !voiceInput.supported
                    ? "Voice input isn't supported in this browser"
                    : voiceInput.listening
                      ? "Stop recording"
                      : "Voice input"
                }
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
                title={
                  !readAloud.supported
                    ? "Read aloud isn't supported in this browser"
                    : readAloud.speaking
                      ? "Stop reading"
                      : input.trim()
                        ? "Read your message aloud"
                        : "Read the last response aloud"
                }
              >
                {readAloud.speaking ? (
                  <Square className="h-3.5 w-3.5" />
                ) : (
                  <AudioLines className="h-3.5 w-3.5" />
                )}
              </button>

              <button
                onClick={() => handleSend()}
                disabled={sending || (!input.trim() && attachments.length === 0)}
                className="p-1.5 bg-primary text-primary-foreground rounded-lg hover:opacity-90 disabled:opacity-50 transition-all ml-1 flex items-center justify-center"
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

// Shown in place of the reply while the agent is searching data / thinking
// — the avatar breathes and the dots bounce so a wait reads as active work
// rather than a stalled UI.
function ThinkingIndicator() {
  return (
    <div className="flex gap-4 animate-fade-in">
      <div className="shrink-0 flex items-start pt-1">
        <div className="w-8 h-8 rounded-full border border-border/35 bg-card flex items-center justify-center overflow-hidden shadow-sm animate-logo-pulse">
          <Image src="/loomverse-mark.png" alt="LoomVerse AI" width={20} height={20} />
        </div>
      </div>
      <div className="flex items-center gap-1 pt-2.5">
        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce-dot" />
        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce-dot delay-100" />
        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce-dot delay-200" />
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  onConfirm,
  onCancel,
  actionBusy,
  animate,
}: {
  message: ChatMessage;
  onConfirm: (message: ChatMessage) => void;
  onCancel: (message: ChatMessage) => void;
  actionBusy: boolean;
  animate: boolean;
}) {
  const isUser = message.role === "user";
  const isUnavailable = !isUser && message.ok === false;

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-[#f0eae1] border border-border/30 px-4 py-2.5 text-sm text-foreground shadow-sm animate-fade-in">
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  // Assistant response
  return (
    <div className="flex gap-4 animate-fade-in">
      {/* LoomVerse Brand mark as avatar */}
      <div className="shrink-0 flex items-start pt-1">
        <div className="w-8 h-8 rounded-full border border-border/35 bg-card flex items-center justify-center overflow-hidden shadow-sm">
          <Image
            src="/loomverse-mark.png"
            alt="LoomVerse AI"
            width={20}
            height={20}
          />
        </div>
      </div>

      <div className="flex-1 min-w-0 pt-1">
        {isUnavailable ? (
          <div className="rounded-xl border border-dashed border-destructive/40 bg-destructive/5 p-3 text-muted-foreground">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-destructive">
              <AlertTriangle className="h-3.5 w-3.5" />
              Not available
            </div>
            <p className="text-sm leading-relaxed">{message.content}</p>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-sm leading-relaxed text-foreground">
              <Streamdown
                mode="static"
                animated={animate ? { sep: "word", stagger: 18, animation: "fadeIn" } : false}
                components={markdownComponents}
              >
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
            {message.action_status === "pending" ? (
              <div className="mt-2.5 flex gap-2">
                <Button
                  size="xs"
                  onClick={() => onConfirm(message)}
                  disabled={actionBusy}
                  className="gap-1 bg-primary text-primary-foreground hover:opacity-90"
                >
                  <Check className="h-3 w-3" />
                  Confirm
                </Button>
                <Button
                  size="xs"
                  variant="outline"
                  onClick={() => onCancel(message)}
                  disabled={actionBusy}
                  className="gap-1 border-border text-foreground hover:bg-muted/50"
                >
                  <X className="h-3 w-3" />
                  Cancel
                </Button>
              </div>
            ) : (
              <p className="mt-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {message.action_status}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
