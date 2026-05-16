/**
 * Refund detail (Phase 6.7b).
 *
 * Read-only summary plus a state-aware action bar. Action availability is
 * gated by both the refund state (pending_approval → approve/reject;
 * approved → post; pending or approved → cancel) and the user's role
 * (post requires owner / bookkeeper).
 *
 * After posting we show the reversing journal-entry id and a basic
 * inventory-restoration breakdown derived from the refund items.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { AxiosError } from "axios";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import type { components } from "@/api/types";
import { useAuthStore } from "@/store/useAuthStore";

type RefundResponse = components["schemas"]["RefundResponse"];

function extractDetail(err: unknown, fallback: string): string {
  const ax = err as AxiosError<{ detail?: string }>;
  return ax?.response?.data?.detail ?? fallback;
}

const ADMIN_ROLES = new Set(["owner", "bookkeeper"]);

export function RefundDetailPage() {
  const { id = "" } = useParams();
  const user = useAuthStore((s) => s.user);
  const [refund, setRefund] = useState<RefundResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  function reload() {
    apiClient
      .get<RefundResponse>(`/api/v1/refunds/${id}`)
      .then((res) => setRefund(res.data))
      .catch((err: unknown) =>
        setError(extractDetail(err, "Failed to load refund.")),
      );
  }

  useEffect(() => {
    if (!id) return;
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function action(path: string, body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/refunds/${id}/${path}`, body);
      reload();
    } catch (err) {
      setError(extractDetail(err, `${path} failed.`));
    } finally {
      setBusy(false);
    }
  }

  if (!refund) {
    return (
      <section className="text-sm text-muted-foreground">
        {error ?? "Loading…"}
      </section>
    );
  }

  const isAdmin = !!user && ADMIN_ROLES.has(user.role);
  const isPending = refund.state === "pending_approval";
  const isApproved = refund.state === "approved";
  const canPost = isAdmin && isApproved;
  const canApproveReject = isAdmin && isPending;
  const canCancel =
    isAdmin && (refund.state === "pending_approval" || refund.state === "approved");

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Refund {refund.refund_number}
        </h1>
        <p className="text-sm text-muted-foreground">
          state: <strong>{refund.state}</strong> · kind: {refund.kind} · reason:{" "}
          {refund.reason_code}
        </p>
      </header>

      {error && (
        <div role="alert" className="rounded border border-destructive p-3 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          Sale:{" "}
          <Link to={`/sales/${refund.sale_id}`} className="text-primary underline">
            {refund.sale_id.slice(0, 8)}…
          </Link>
        </div>
        <div>Total: {refund.total_amount}</div>
        <div>Created: {new Date(refund.created_at).toLocaleString()}</div>
        <div>Restock inventory: {refund.restock_inventory ? "yes" : "no"}</div>
        {refund.approval_request_id && (
          <div className="col-span-2">
            Approval request:{" "}
            <Link
              to={`/approvals/${refund.approval_request_id}`}
              className="text-primary underline"
            >
              {refund.approval_request_id}
            </Link>
          </div>
        )}
        {refund.posting_journal_entry_id && (
          <div className="col-span-2">
            Posted journal entry:{" "}
            <Link
              to={`/accounting/entries/${refund.posting_journal_entry_id}`}
              className="text-primary underline"
              data-testid="posted-je-link"
            >
              {refund.posting_journal_entry_id}
            </Link>
          </div>
        )}
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="py-2">Sale item</th>
            <th>Quantity</th>
            <th>Unit amount</th>
            <th className="text-right">Extended</th>
          </tr>
        </thead>
        <tbody>
          {(refund.items ?? []).map((item) => (
            <tr key={item.id} className="border-t border-border">
              <td className="py-2">{item.sale_item_id.slice(0, 8)}…</td>
              <td>{item.quantity}</td>
              <td>{item.unit_amount}</td>
              <td className="text-right">{item.extended_amount}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {refund.state === "posted" && refund.restock_inventory && (
        <div
          data-testid="inventory-restoration"
          className="rounded border border-border p-3 text-sm"
        >
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Inventory restored
          </h2>
          <ul className="mt-2 list-disc pl-5">
            {(refund.items ?? []).map((item) => (
              <li key={item.id}>
                Line {item.sale_item_id.slice(0, 8)}…: +{item.quantity}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(canApproveReject || canPost || canCancel) && (
        <div className="flex flex-col gap-2 rounded border border-border p-3">
          <label className="text-sm">
            Decision note
            <textarea
              data-testid="refund-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="mt-1 block w-full rounded border border-border bg-background p-2 text-sm"
              rows={2}
            />
          </label>
          <div className="flex gap-2">
            {canApproveReject && (
              <>
                <Button
                  type="button"
                  data-testid="refund-approve"
                  disabled={busy}
                  onClick={() => void action("approve", { note: note || null })}
                >
                  Approve
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  data-testid="refund-reject"
                  disabled={busy}
                  onClick={() => void action("reject", { note: note || null })}
                >
                  Reject
                </Button>
              </>
            )}
            {canPost && (
              <Button
                type="button"
                data-testid="refund-post"
                disabled={busy}
                onClick={() => void action("post", {})}
              >
                Post
              </Button>
            )}
            {canCancel && (
              <Button
                type="button"
                variant="destructive"
                data-testid="refund-cancel"
                disabled={busy}
                onClick={() => void action("cancel", {})}
              >
                Cancel
              </Button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
