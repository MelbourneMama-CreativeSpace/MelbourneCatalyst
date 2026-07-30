"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { MessageSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import { createConversation } from "@/lib/api";

export default function ChatIndexPage() {
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  async function handleStart() {
    setCreating(true);
    try {
      const conversation = await createConversation();
      router.push(`/chat/${conversation.id}`);
    } catch {
      setCreating(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-4 px-6 py-24 text-center">
      <MessageSquare className="h-10 w-10 text-primary" />
      <div>
        <h1 className="text-xl font-semibold">Ask LoomVerse AI</h1>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          Ask about trending topics, a client&apos;s profile, or what&apos;s in the
          content pipeline — it can look up your real data to answer.
        </p>
      </div>
      <Button onClick={handleStart} disabled={creating}>
        {creating ? "Starting…" : "Start a conversation"}
      </Button>
    </div>
  );
}
