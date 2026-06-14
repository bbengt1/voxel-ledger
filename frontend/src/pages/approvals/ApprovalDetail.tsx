/**
 * Approval-request detail page (Phase 4.4, polished in Phase 4.6).
 *
 * Renders a type-aware payload for known request types (currently:
 * ``accounting.large_journal_entry``) and falls back to a raw JSON
 * ``<pre>`` for anything else. Adds a "Post entry now" action when the
 * request is approved + not yet consumed + the journal-entry type.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import {
  JournalEntryPayloadRenderer,
  type JournalEntryPayload,
} from "@/components/accounting/JournalEntryPayloadRenderer";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

interface ApprovalDetail {
  id: string;
  request_type: string;
  subject_kind: string;
  subject_id: string;
  requested_by_user_id: string;
  requested_at: string;
  state: "pending" | "approved" | "rejected" | "cancelled";
  decided_by_user_id: string | null;
  decided_at: string | null;
  decision_note: string | null;
  payload: Record<string, unknown>;
  threshold_amount: string | null;
  consumed_at: string | null;
}

const POST_ENTRY_ROLES = new Set(["owner", "bookkeeper"]);
const LARGE_JE_TYPE = "accounting.large_journal_entry";

export function ApprovalDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [row, setRow] = useState<ApprovalDetail | null>(null);
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = () => {
    apiClient
      .get<ApprovalDetail>(`/api/v1/approvals/${id}`)
      .then((res) => setRow(res.data))
      .catch((err: unknown) => {
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load approval.";
        setError(msg);
      });
  };

  useEffect(() => {
    if (!id) return;
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const isAdmin = user?.role === "owner" || user?.role === "bookkeeper";
  const isRequester = !!row && !!user && row.requested_by_user_id === user.id;
  const isPending = row?.state === "pending";

  const post = async (path: string, body: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/approvals/${id}/${path}`, body);
      reload();
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Action failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  async function postEntryNow() {
    if (!row) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/accounting/entries/from-approval/${row.id}`, {});
      // QBO replace-mode (#318 5e-2): the journal-entry detail page was
      // removed — return to the approvals list after posting.
      navigate("/approvals");
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Post entry failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  if (!row) {
    return (
      <section className="text-sm text-muted-foreground">
        {error ?? "Loading…"}
      </section>
    );
  }

  const approveDisabled =
    busy || !isPending || !isAdmin || isRequester;
  const rejectDisabled = approveDisabled;
  const cancelDisabled =
    busy || !isPending || !(isRequester || user?.role === "owner");

  const canPostEntry =
    !!user &&
    POST_ENTRY_ROLES.has(user.role) &&
    row.request_type === LARGE_JE_TYPE &&
    row.state === "approved" &&
    row.consumed_at === null;

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Approval request
        </h1>
        <p className="text-sm text-muted-foreground">
          {row.request_type} • state: <strong>{row.state}</strong>
        </p>
      </header>

      {error && (
        <div role="alert" className="rounded border border-destructive p-3 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>Subject: {row.subject_kind}:{row.subject_id}</div>
        <div>Requested at: {new Date(row.requested_at).toLocaleString()}</div>
        <div>Requested by: {row.requested_by_user_id}</div>
        <div>Threshold: {row.threshold_amount ?? "—"}</div>
        {row.decided_at && (
          <>
            <div>Decided at: {new Date(row.decided_at).toLocaleString()}</div>
            <div>Decided by: {row.decided_by_user_id ?? "—"}</div>
          </>
        )}
        {row.consumed_at && (
          <div className="col-span-2">
            Consumed at: {new Date(row.consumed_at).toLocaleString()}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Payload
        </h2>
        {row.request_type === LARGE_JE_TYPE ? (
          <JournalEntryPayloadRenderer
            payload={row.payload as unknown as JournalEntryPayload}
          />
        ) : (
          <pre
            data-testid="payload"
            className="mt-1 max-h-96 overflow-auto rounded border border-border bg-muted/30 p-3 text-xs"
          >
            {JSON.stringify(row.payload, null, 2)}
          </pre>
        )}
      </div>

      {canPostEntry && (
        <div>
          <Button
            type="button"
            onClick={postEntryNow}
            disabled={busy}
            data-testid="post-entry-now"
          >
            Post entry now
          </Button>
        </div>
      )}

      {isPending && (
        <div className="flex flex-col gap-2">
          <label className="text-sm">
            Decision note / reason
            <textarea
              data-testid="decision-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="mt-1 block w-full rounded border border-border bg-background p-2 text-sm"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              data-testid="approve-btn"
              disabled={approveDisabled}
              title={
                isRequester
                  ? "You cannot approve your own request"
                  : !isAdmin
                    ? "Requires owner or bookkeeper"
                    : ""
              }
              onClick={() => post("approve", { decision_note: note || null })}
              className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground disabled:opacity-50"
            >
              Approve
            </button>
            <button
              type="button"
              data-testid="reject-btn"
              disabled={rejectDisabled}
              title={
                isRequester
                  ? "You cannot reject your own request"
                  : !isAdmin
                    ? "Requires owner or bookkeeper"
                    : ""
              }
              onClick={() => post("reject", { decision_note: note || null })}
              className="rounded border border-border px-3 py-1 text-sm disabled:opacity-50"
            >
              Reject
            </button>
            <button
              type="button"
              data-testid="cancel-btn"
              disabled={cancelDisabled}
              onClick={() => post("cancel", { reason: note || null })}
              className="rounded border border-border px-3 py-1 text-sm disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
