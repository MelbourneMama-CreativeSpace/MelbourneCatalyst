"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Mic, Paperclip, ChevronDown, AudioLines, Send, Square, X, FileIcon } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { createConversation, uploadChatAttachment, type ChatAttachment } from "@/lib/api";
import { useReadAloud, useVoiceInput } from "@/hooks/use-speech";
import { cn } from "@/lib/utils";

export default function ChatIndexPage() {
  const router = useRouter();
  const [userName, setUserName] = useState("User");
  const [greeting, setGreeting] = useState("Hello");
  const [input, setInput] = useState("");
  const [creating, setCreating] = useState(false);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const voiceInput = useVoiceInput((transcript) =>
    setInput((prev) => (prev ? `${prev} ${transcript}` : transcript)),
  );
  const readAloud = useReadAloud();

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user) {
        const name = user.user_metadata?.full_name || user.email?.split("@")[0] || "User";
        setUserName(name);
      }
    });

    const hour = new Date().getHours();
    if (hour < 12) setGreeting("Morning");
    else if (hour < 17) setGreeting("Afternoon");
    else setGreeting("Evening");
  }, []);

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setUploading(true);
    setUploadError(null);
    try {
      const attachment = await uploadChatAttachment(file);
      setAttachments((prev) => [...prev, attachment]);
    } catch (err) {
      setUploadError(
        err instanceof Error && err.message.includes("409")
          ? "Media storage isn't configured on the backend."
          : "Couldn't upload that file — try again.",
      );
    } finally {
      setUploading(false);
    }
  }

  function removeAttachment(url: string) {
    setAttachments((prev) => prev.filter((a) => a.url !== url));
  }

  async function handleStartChat(textToSend: string) {
    if ((!textToSend.trim() && attachments.length === 0) || creating) return;
    setCreating(true);
    try {
      const attachmentMd = attachments
        .map((a) =>
          a.content_type.startsWith("image/")
            ? `![${a.filename}](${a.url})`
            : `[${a.filename}](${a.url})`,
        )
        .join("\n");
      const content = [textToSend.trim(), attachmentMd].filter(Boolean).join("\n\n");
      const conversation = await createConversation();
      // Stage the message rather than sending it here, then navigate
      // straight away — the conversation page picks it up and sends it
      // itself, so this first exchange gets the same animated
      // send/scroll/thinking-indicator treatment as every later one
      // instead of arriving already resolved.
      sessionStorage.setItem(`loomverse:pending-message:${conversation.id}`, content);
      router.push(`/chat/${conversation.id}`);
    } catch {
      setCreating(false);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-background text-foreground transition-colors duration-300">
      {/* Top right header like Claude's "Free plan . Upgrade" */}
      <div className="flex justify-between items-center px-6 py-4">
        <div></div> {/* Spacer */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground bg-muted/40 rounded-full px-3 py-1 font-medium border border-border/40">
            Free plan &bull; Upgrade
          </span>
        </div>
      </div>

      {/* Main greeting + input container */}
      <div className="flex flex-1 flex-col items-center justify-center px-6 pb-32">
        {/* Splash Greeting */}
        <div className="flex items-center justify-center gap-4 mb-8">
          <Image
            src="/loomverse-mark.png"
            alt="LoomVerse logo"
            width={48}
            height={48}
            className="shrink-0 animate-fade-in"
          />
          <h1 className="text-4xl md:text-5xl font-normal tracking-tight claude-serif text-foreground">
            {greeting}, {userName}
          </h1>
        </div>

        {/* Input box */}
        <div className="w-full max-w-2xl bg-card border border-border shadow-md rounded-2xl p-4 flex flex-col gap-3 focus-within:ring-2 focus-within:ring-ring/25 focus-within:border-border/90 transition-all duration-200">

          {/* Attachment previews */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2">
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
                handleStartChat(input);
              }
            }}
            placeholder="Type / for skills"
            rows={3}
            disabled={creating}
            className="w-full resize-none bg-transparent text-base text-foreground outline-none placeholder:text-muted-foreground/75"
          />

          {uploadError && (
            <p className="text-xs text-destructive">{uploadError}</p>
          )}

          <div className="flex items-center justify-between border-t border-border/5 pt-3">
            {/* Bottom left actions */}
            <div className="flex items-center gap-2">
              {/* Hidden file input */}
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelected}
                disabled={uploading || creating}
                accept="image/*,video/*,application/pdf,.doc,.docx,.txt,.csv,.xls,.xlsx"
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || creating}
                className={cn(
                  "p-2 rounded-lg transition-colors",
                  uploading
                    ? "text-primary animate-pulse cursor-wait"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                  (uploading || creating) && "disabled:opacity-40 disabled:cursor-not-allowed",
                )}
                title={uploading ? "Uploading…" : "Attach a file"}
              >
                <Paperclip className="h-5 w-5" />
              </button>
            </div>

            {/* Bottom right actions */}
            <div className="flex items-center gap-3">
              {/* Model selection pill */}
              <button
                type="button"
                disabled
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-muted-foreground/40 rounded-full border border-border/40 cursor-not-allowed"
                title="Model switching isn't available yet"
              >
                <span>Sonnet 5 Medium</span>
                <ChevronDown className="h-3 w-3" />
              </button>

              <button
                type="button"
                onClick={voiceInput.toggle}
                disabled={!voiceInput.supported}
                className={`p-2 rounded-lg transition-colors ${
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
                <Mic className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={() =>
                  readAloud.speaking ? readAloud.stop() : readAloud.speak(input)
                }
                disabled={!readAloud.supported || (!readAloud.speaking && !input.trim())}
                className={`p-2 rounded-lg transition-colors ${
                  readAloud.speaking
                    ? "text-primary bg-primary/10"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
                title={
                  !readAloud.supported
                    ? "Read aloud isn't supported in this browser"
                    : readAloud.speaking
                      ? "Stop reading"
                      : "Read your message aloud"
                }
              >
                {readAloud.speaking ? (
                  <Square className="h-4 w-4" />
                ) : (
                  <AudioLines className="h-4 w-4" />
                )}
              </button>

              <button
                type="button"
                onClick={() => handleStartChat(input)}
                disabled={(!input.trim() && attachments.length === 0) || creating}
                className="p-2 bg-primary text-primary-foreground rounded-lg hover:opacity-90 disabled:opacity-50 transition-all flex items-center justify-center"
                title="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
