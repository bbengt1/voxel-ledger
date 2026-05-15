/**
 * Journal entry composer.
 *
 * - Live debit/credit balance display.
 * - Submit disabled until balanced + accounts picked + xor debit/credit.
 * - Branches on the response status: 201 → entry detail, 202 → approval
 *   banner, anything else → inline detail.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import {
  JournalLineGrid,
  emptyLines,
  isReadyToSubmit,
  type JournalLineDraft,
} from "@/components/accounting/JournalLineGrid";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type JournalEntryResponse = components["schemas"]["JournalEntryResponse"];
type PendingApproval =
  components["schemas"]["JournalEntryPendingApprovalResponse"];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function JournalEntryComposerPage() {
  const navigate = useNavigate();
  const [description, setDescription] = useState("");
  const [postedDate, setPostedDate] = useState<string>(today());
  const [lines, setLines] = useState<JournalLineDraft[]>(() => emptyLines(2));
  const [error, setError] = useState<string | null>(null);
  const [pendingApprovalId, setPendingApprovalId] = useState<string | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  const canSubmit =
    !busy && description.trim().length > 0 && isReadyToSubmit(lines);

  async function submit() {
    setBusy(true);
    setError(null);
    setPendingApprovalId(null);
    const payload = {
      description: description.trim(),
      // Backend expects an ISO datetime; coerce date-only to midnight UTC.
      posted_at: new Date(`${postedDate}T00:00:00Z`).toISOString(),
      lines: lines.map((ln, idx) => ({
        account_id: ln.account!.id,
        debit: ln.debit || "0",
        credit: ln.credit || "0",
        memo: ln.memo || null,
        division_id: ln.divisionId || null,
        line_number: idx + 1,
      })),
    };
    try {
      const res = await apiClient.post<JournalEntryResponse | PendingApproval>(
        "/api/v1/accounting/entries",
        payload,
      );
      if (res.status === 202) {
        const pending = res.data as PendingApproval;
        setPendingApprovalId(pending.approval_request_id);
        return;
      }
      const entry = res.data as JournalEntryResponse;
      navigate(`/accounting/entries/${entry.id}`);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to post entry.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">New journal entry</h1>
        <Button asChild variant="outline">
          <Link to="/accounting/entries">Back to list</Link>
        </Button>
      </header>

      {pendingApprovalId ? (
        <div
          role="status"
          data-testid="approval-banner"
          className="rounded border border-amber-500/40 bg-amber-50 p-3 text-sm dark:bg-amber-900/20"
        >
          Approval request created —{" "}
          <Link
            to={`/approvals/${pendingApprovalId}`}
            className="underline"
            data-testid="approval-link"
          >
            request #{pendingApprovalId.slice(0, 8)}
          </Link>{" "}
          is pending.
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          data-testid="composer-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs">
          Description
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. October utility expense"
            data-testid="entry-description"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Posted at
          <Input
            type="date"
            value={postedDate}
            onChange={(e) => setPostedDate(e.target.value)}
            data-testid="entry-posted-at"
          />
        </label>
      </div>

      <JournalLineGrid lines={lines} onChange={setLines} />

      <div className="flex justify-end">
        <Button
          onClick={submit}
          disabled={!canSubmit}
          data-testid="submit-entry"
        >
          Post entry
        </Button>
      </div>
    </section>
  );
}
