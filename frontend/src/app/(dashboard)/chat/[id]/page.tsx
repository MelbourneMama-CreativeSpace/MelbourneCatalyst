"use client";

import { notFound, useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { ApiError } from "@/lib/api-error";
import { getConversation, type ConversationDetail } from "@/lib/api";

export default function ChatConversationPage() {
  const { id } = useParams<{ id: string }>();
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<"not-found" | "unknown" | null>(null);

  useEffect(() => {
    let cancelled = false;
    getConversation(id)
      .then((data) => {
        if (!cancelled) setConversation(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError && err.status === 404 ? "not-found" : "unknown");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error === "not-found") notFound();

  if (error === "unknown") {
    return (
      <div className="px-6 py-10 text-sm text-muted-foreground">
        Couldn&apos;t load this conversation — try again.
      </div>
    );
  }

  if (!conversation) {
    return <div className="px-6 py-10 text-sm text-muted-foreground">Loading…</div>;
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="border-b border-border px-6 py-4">
        <h1 className="truncate text-sm font-medium">
          {conversation.title ?? "New conversation"}
        </h1>
      </div>
      <div className="flex-1 min-h-0">
        <ChatPanel conversationId={conversation.id} initialMessages={conversation.messages} />
      </div>
    </div>
  );
}
