"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { describeError } from "@/lib/api-error";
import {
  inviteCompanyMember,
  listCompanyMembers,
  removeCompanyMember,
  type CompanyMember,
} from "@/lib/api";

/**
 * Who can see and act on this company.
 *
 * Two states worth distinguishing in the UI, because they behave
 * differently: a real member (has a `user_id`) has access right now; an
 * invite (`user_id` null) has none at all until that person signs in with
 * the matching email — this app has no way to turn an email into a
 * Supabase user id on its own, and no way to send them mail either, so
 * the copy below says so rather than implying an email went out.
 */
export function MembersPanel({ companyId }: { companyId: string }) {
  const [members, setMembers] = useState<CompanyMember[]>([]);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listCompanyMembers(companyId)
      .then(({ items, current_user_id }) => {
        setMembers(items);
        setCurrentUserId(current_user_id);
      })
      .catch(() => {});
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function handleInvite(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;

    setInviting(true);
    setError(null);
    try {
      await inviteCompanyMember(companyId, trimmed);
      setEmail("");
      refresh();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setInviting(false);
    }
  }

  async function handleRemove(memberId: string) {
    setError(null);
    try {
      await removeCompanyMember(companyId, memberId);
      refresh();
    } catch (err) {
      setError(describeError(err));
    }
  }

  const realMemberCount = members.filter((m) => m.user_id !== null).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">Who has access</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {members.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nobody has claimed this client yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {members.map((member) => {
              const isYou = member.user_id !== null && member.user_id === currentUserId;
              const pending = member.user_id === null;
              return (
                <li
                  key={member.id}
                  className="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
                >
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-sm">
                      {member.user_email ?? member.invited_email ?? "Unknown"}
                      {isYou && <span className="text-muted-foreground"> (you)</span>}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {pending
                        ? "Invited — gets access the first time they sign in"
                        : member.role}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {pending && <Badge variant="outline">Pending</Badge>}
                    {/* Removing the last real member would return this
                        company to "unclaimed" — visible to everyone
                        again — so the backend refuses it and the button
                        is hidden rather than offered and rejected. */}
                    {!(member.user_id !== null && realMemberCount === 1) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemove(member.id)}
                      >
                        Remove
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <form onSubmit={handleInvite} className="flex gap-2">
          <Input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="teammate@example.com"
            aria-label="Invite a teammate by email"
          />
          <Button type="submit" disabled={inviting || !email.trim()}>
            {inviting ? "Inviting…" : "Invite"}
          </Button>
        </form>

        <p className="text-xs text-muted-foreground">
          No email is sent — tell them yourself. They get access the first time
          they sign in with this address.
        </p>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
