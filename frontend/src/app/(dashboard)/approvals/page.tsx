"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, User, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  listPendingApprovals,
  updateContentItem,
  updateStrategyApproval,
  type PendingApproval,
} from "@/lib/api";

// Same localStorage key used by content-plan-view.tsx/strategy-view.tsx for
// approved_by — one "who's using this browser" identity, not duplicated.
const APPROVER_NAME_STORAGE_KEY = "mmcs_approver_name";

function detailHref(item: PendingApproval): string {
  return item.type === "strategy" ? `/strategy/${item.id}` : `/companies/${item.company_id}`;
}

export default function ApprovalsPage() {
  const [items, setItems] = useState<PendingApproval[] | null>(null);
  const [error, setError] = useState(false);
  const [actingOn, setActingOn] = useState<string | null>(null);
  const [approverName, setApproverName] = useState("");
  const [showMineOnly, setShowMineOnly] = useState(false);

  useEffect(() => {
    listPendingApprovals()
      .then((res) => setItems(res.items))
      .catch(() => setError(true));
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setApproverName(localStorage.getItem(APPROVER_NAME_STORAGE_KEY) ?? "");
  }, []);

  async function handleDecision(item: PendingApproval, decision: "approved" | "rejected") {
    setActingOn(item.id);
    try {
      if (item.type === "strategy") {
        await updateStrategyApproval(item.id, decision);
      } else {
        await updateContentItem(item.id, { approvalStatus: decision });
      }
      setItems((prev) => prev?.filter((i) => i.id !== item.id) ?? null);
    } catch {
      // Leave the item in the list — the user can retry.
    } finally {
      setActingOn(null);
    }
  }

  async function handleAssignToMe(item: PendingApproval) {
    if (!approverName.trim()) return;
    setActingOn(item.id);
    try {
      if (item.type === "strategy") {
        await updateStrategyApproval(item.id, "pending", undefined, approverName);
      } else {
        await updateContentItem(item.id, { reviewer: approverName });
      }
      setItems(
        (prev) => prev?.map((i) => (i.id === item.id ? { ...i, reviewer: approverName } : i)) ?? null,
      );
    } catch {
      // Leave as-is — the user can retry.
    } finally {
      setActingOn(null);
    }
  }

  const visibleItems =
    showMineOnly && approverName
      ? items?.filter((i) => i.reviewer === approverName)
      : items;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold">Approvals</h1>
      <p className="mt-1 text-muted-foreground">
        Everything waiting on a decision, across every client.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          value={approverName}
          onChange={(e) => {
            setApproverName(e.target.value);
            localStorage.setItem(APPROVER_NAME_STORAGE_KEY, e.target.value);
          }}
          placeholder="Your name"
          className="w-40 rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring"
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            variant={showMineOnly ? "outline" : "default"}
            onClick={() => setShowMineOnly(false)}
          >
            All
          </Button>
          <Button
            size="sm"
            variant={showMineOnly ? "default" : "outline"}
            onClick={() => setShowMineOnly(true)}
            disabled={!approverName.trim()}
          >
            Mine
          </Button>
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-3">
        {error && (
          <p className="text-sm text-destructive">Couldn&apos;t load the approval queue.</p>
        )}
        {visibleItems !== null && visibleItems?.length === 0 && !error && (
          <p className="text-sm text-muted-foreground">
            {showMineOnly ? "Nothing assigned to you." : "Nothing pending — you're caught up."}
          </p>
        )}
        {visibleItems?.map((item) => (
          <Card key={`${item.type}-${item.id}`}>
            <CardContent className="flex items-center justify-between gap-4 py-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="capitalize">
                    {item.type === "strategy" ? "Strategy" : "Content"}
                  </Badge>
                  <span className="text-sm text-muted-foreground">
                    {item.company_name ?? "Unknown company"}
                  </span>
                  {item.reviewer && (
                    <Badge variant="outline" className="gap-1">
                      <User className="h-3 w-3" />
                      {item.reviewer}
                    </Badge>
                  )}
                </div>
                <Link href={detailHref(item)} className="mt-1 block truncate text-sm font-medium hover:underline">
                  {item.title}
                </Link>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {item.reviewer !== approverName && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={actingOn === item.id || !approverName.trim()}
                    onClick={() => handleAssignToMe(item)}
                  >
                    Assign to me
                  </Button>
                )}
                <Button
                  size="icon-sm"
                  variant="ghost"
                  disabled={actingOn === item.id}
                  onClick={() => handleDecision(item, "approved")}
                  aria-label="Approve"
                >
                  <Check className="h-4 w-4 text-primary" />
                </Button>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  disabled={actingOn === item.id}
                  onClick={() => handleDecision(item, "rejected")}
                  aria-label="Reject"
                >
                  <X className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
