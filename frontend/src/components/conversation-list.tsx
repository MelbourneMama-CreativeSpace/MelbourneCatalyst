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
    listConversations()
      .then((res) => {
        if (!cancelled) setConversations(res.items);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
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

  if (conversations.length === 0) {
    return <p className="px-3 text-xs text-sidebar-foreground/50">No conversations yet.</p>;
  }

  return (
    <div className="flex flex-col gap-0.5">
      {conversations.map((c) => {
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
            {c.title ?? "New conversation"}
          </Link>
        );
      })}
    </div>
  );
}
