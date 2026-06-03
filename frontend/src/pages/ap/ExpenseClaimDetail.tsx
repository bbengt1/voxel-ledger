/**
 * `/expense-claims/:id` — claim detail. Lines table + state action bar
 * with role + state gating:
 *   submitter on draft     → Submit / Cancel
 *   submitter on submitted → Cancel
 *   owner/bookkeeper on submitted → Approve / Reject
 *   owner/bookkeeper on approved  → Mark reimbursed
 * Self-approval guard: hides Approve when actor.id == submitter_user_id.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type ExpenseClaimResponse = components["schemas"]["ExpenseClaimResponse"];

const ADMIN_ROLES: readonly string[] = ["owner", "bookkeeper"];

export function ExpenseClaimDetailPage() {
  const { id } = useParams<{ id: string }>();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role ? ADMIN_ROLES.includes(user.role) : false;

  const [claim, setClaim] = useState<ExpenseClaimResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [reimburseInput, setReimburseInput] = useState("");

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/expense-claims/${id}` as "/api/v1/expense-claims/{claim_id}",
      );
      setClaim(res.data as unknown as ExpenseClaimResponse);
    } catch {
      setError("Failed to load claim.");
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function postAction(
    path: string,
    label: string,
    body?: unknown,
  ): Promise<void> {
    if (!id) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiClient.post(
        `/api/v1/expense-claims/${id}/${path}`,
        body ?? null,
      );
      setNotice(`${label} succeeded.`);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : `Could not ${label}.`);
    } finally {
      setBusy(false);
    }
  }

  function reject() {
    void postAction("reject", "Reject", {
      rejection_reason: rejectionReason.trim() || null,
    });
  }

  function markReimbursed() {
    if (!reimburseInput.trim()) {
      setError("Provide a bill payment id.");
      return;
    }
    void postAction("mark-reimbursed", "Mark reimbursed", {
      bill_payment_id: reimburseInput.trim(),
    });
  }

  if (!claim) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">Loading…</p>
    );
  }

  const isSubmitter = user?.id === claim.submitter_user_id;
  const isDraft = claim.state === "draft";
  const isSubmitted = claim.state === "submitted";
  const isApproved = claim.state === "approved";
  const canSubmitterAct = isSubmitter && (isDraft || isSubmitted);
  const canApprove = isAdmin && isSubmitted && !isSubmitter;
  const canReject = isAdmin && isSubmitted;
  const canMarkReimbursed = isAdmin && isApproved;

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{claim.claim_number}</h1>
          <p className="text-sm text-muted-foreground">
            State: <span data-testid="claim-state">{claim.state}</span> ·
            total ${claim.total_amount}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/expense-claims">Back</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p
          role="status"
          className="rounded border border-border bg-muted/30 p-3 text-sm"
          data-testid="claim-notice"
        >
          {notice}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2" data-testid="claim-actions">
        {canSubmitterAct && isDraft ? (
          <Button
            disabled={busy}
            onClick={() => void postAction("submit", "Submit")}
            data-testid="action-submit"
          >
            Submit
          </Button>
        ) : null}
        {canSubmitterAct ? (
          <Button
            variant="destructive"
            disabled={busy}
            onClick={() => {
              if (!window.confirm("Cancel this claim?")) return;
              void postAction("cancel", "Cancel");
            }}
            data-testid="action-cancel"
          >
            Cancel
          </Button>
        ) : null}
        {canApprove ? (
          <Button
            disabled={busy}
            onClick={() => void postAction("approve", "Approve")}
            data-testid="action-approve"
          >
            Approve
          </Button>
        ) : null}
        {canReject ? (
          <Button
            variant="destructive"
            disabled={busy}
            onClick={reject}
            data-testid="action-reject"
          >
            Reject
          </Button>
        ) : null}
      </div>

      {canReject ? (
        <label className="block text-xs">
          Rejection reason (optional)
          <Input
            value={rejectionReason}
            onChange={(e) => setRejectionReason(e.target.value)}
            data-testid="rejection-reason"
          />
        </label>
      ) : null}

      {canMarkReimbursed ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="block text-xs">
            Bill payment id
            <Input
              value={reimburseInput}
              onChange={(e) => setReimburseInput(e.target.value)}
              placeholder="uuid"
              data-testid="reimburse-bill-payment-id"
            />
          </label>
          <Button
            disabled={busy}
            onClick={markReimbursed}
            data-testid="action-mark-reimbursed"
          >
            Mark reimbursed
          </Button>
        </div>
      ) : null}

      <div className="rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Lines</h2>
        <div className="overflow-x-auto">
          <table className="mt-2 w-full min-w-[36rem] table-fixed border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-2">#</th>
                <th className="py-2 pr-2">Description</th>
                <th className="py-2 pr-2">Occurred</th>
                <th className="py-2 pr-2">Billable</th>
                <th className="py-2 pr-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {(claim.lines ?? []).map((l) => (
                <tr key={l.id} className="border-b border-border/50">
                  <td className="py-2 pr-2 font-mono text-xs">
                    {l.line_number}
                  </td>
                  <td className="py-2 pr-2">{l.description}</td>
                  <td className="py-2 pr-2 text-xs">
                    {new Date(l.occurred_on).toLocaleDateString()}
                  </td>
                  <td className="py-2 pr-2">{l.is_billable ? "yes" : "no"}</td>
                  <td className="py-2 pr-2 text-right font-mono">
                    ${l.amount}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
