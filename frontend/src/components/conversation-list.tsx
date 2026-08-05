"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { listConversations, type Conversation } from "@/lib/api";

export function ConversationList() {
  const pathname = usePathname();
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    function refetch() {
      listConversations()
        .then((res) => {
          if (!cancelled) setConversations(res.items);
        })
        .catch(() => {
          if (!cancelled) setError(true);
        });
    }

    refetch();
    // Also refetch on demand — e.g. the moment the backend renames a
    // conversation from the raw first message to something reflecting
    // its actual intent, instead of waiting for the next route change.
    window.addEventListener("loomverse:conversations-updated", refetch);
    return () => {
      cancelled = true;
      window.removeEventListener("loomverse:conversations-updated", refetch);
    };
    // Re-fetch whenever the route changes, so a newly-created conversation
    // shows up as soon as its detail page loads.
  }, [pathname]);

  if (error) {
    return <p className="px-3 text-xs text-sidebar-foreground/50">Couldn&apos;t load conversations.</p>;
  }

  if (conversations === null) {
    return <p className="px-3 text-xs text-sidebar-foreground/50">Loading…</p>;
  }

  // A conversation only gets a title once its first exchange actually
  // completes — the backend sets both together, right after the
  // assistant's reply comes back (see send_message: title generation and
  // run_chat_turn are awaited before the same final commit). So `title
  // === null` reliably means "nothing round-tripped yet" — created (or
  // abandoned before sending), possibly with a lone unanswered user
  // message, but never a real back-and-forth. Those don't belong in
  // history at all, not even as "New conversation" placeholders.
  const completedConversations = conversations.filter((c) => c.title !== null);

  if (completedConversations.length === 0) {
    return <p className="px-3 text-xs text-sidebar-foreground/50">No conversations yet.</p>;
  }

  return (
    <div className="flex flex-col gap-0.5">
      {completedConversations.map((c) => {
        const active = pathname === `/chat/${c.id}`;
        return (
          <Link
            key={c.id}
            href={`/chat/${c.id}`}
            className={`truncate rounded-lg px-3 py-1.5 text-sm transition-colors ${
              active
                ? "bg-sidebar-accent text-sidebar-foreground"
                : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
            }`}
          >
            {c.title}
          </Link>
        );
      })}
    </div>
  );
}
