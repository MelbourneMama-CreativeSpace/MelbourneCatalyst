"use client";

import { useRef, useState } from "react";
import { AlertTriangle, Check, Send, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  cancelAction,
  confirmAction,
  getConversation,
  sendMessage,
  type ChatMessage,
} from "@/lib/api";

export function ChatPanel({
  conversationId,
  initialMessages,
}: {
  conversationId: string;
  initialMessages: ChatMessage[];
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionPendingId, setActionPendingId] = useState<string | null>(null);
  const nextTempId = useRef(0);

  async function handleSend() {
    const content = input.trim();
    if (!content || sending) return;

    setError(null);
    setInput("");
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
      ok: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticMessage]);

    try {
      const assistantMessage = await sendMessage(conversationId, content);
      setMessages((prev) => [...prev, assistantMessage]);
    } catch {
      setError("Couldn't send that — try again.");
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
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Ask a question about your companies, trends, or content pipeline.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
                actionBusy={actionPendingId === message.id}
              />
            ))}
          </div>
        )}
      </div>

      {error && <p className="px-6 pb-2 text-sm text-destructive">{error}</p>}

      <div className="flex items-end gap-2 border-t border-border px-6 py-4">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask anything…"
          rows={1}
          disabled={sending}
          className="flex-1 resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />
        <Button onClick={handleSend} disabled={sending || !input.trim()} size="icon">
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  onConfirm,
  onCancel,
  actionBusy,
}: {
  message: ChatMessage;
  onConfirm: (message: ChatMessage) => void;
  onCancel: (message: ChatMessage) => void;
  actionBusy: boolean;
}) {
  const isUser = message.role === "user";
  // ok === false means this is a graceful-degradation reply (e.g. no
  // Claude credit), not a real answer — render it visibly distinct so
  // it never reads as a genuine response, matching the honest-UI
  // convention used throughout this app (e.g. Company's
  // complete_no_profile state).
  const isUnavailable = !isUser && message.ok === false;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
          isUser
            ? "bg-primary text-primary-foreground"
            : isUnavailable
              ? "border border-dashed border-destructive/40 bg-destructive/5 text-muted-foreground"
              : message.proposed_action
                ? "border border-primary/30 bg-primary/5 text-card-foreground"
                : "bg-card text-card-foreground"
        }`}
      >
        {isUnavailable && (
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-destructive">
            <AlertTriangle className="h-3.5 w-3.5" />
            Not available
          </div>
        )}
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.tool_calls_summary && message.tool_calls_summary.length > 0 && (
          <p className="mt-1.5 text-xs text-muted-foreground">
            Used: {message.tool_calls_summary.join(", ")}
          </p>
        )}

        {message.proposed_action && (
          <div className="mt-3 rounded-lg border border-primary/20 bg-background/60 p-2.5">
            <p className="text-xs font-medium text-foreground">
              {message.proposed_action.description}
            </p>
            {message.action_status === "pending" ? (
              <div className="mt-2 flex gap-2">
                <Button
                  size="xs"
                  onClick={() => onConfirm(message)}
                  disabled={actionBusy}
                  className="gap-1"
                >
                  <Check className="h-3 w-3" />
                  Confirm
                </Button>
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={() => onCancel(message)}
                  disabled={actionBusy}
                  className="gap-1"
                >
                  <X className="h-3 w-3" />
                  Cancel
                </Button>
              </div>
            ) : (
              <p className="mt-1.5 text-xs capitalize text-muted-foreground">
                {message.action_status}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
