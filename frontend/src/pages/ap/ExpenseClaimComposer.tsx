/**
 * `/expense-claims/new` — composer for an expense claim. Header (notes,
 * currency) + dynamic line table (expense category picker, description,
 * amount, occurred-on, optional attachment id, billable flag with
 * customer + markup).
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import {
  CustomerPicker,
  type CustomerOption,
} from "@/components/ar/CustomerPicker";
import { ExpenseCategoryPicker } from "@/components/ap/ExpenseCategoryPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ExpenseClaimCreate = components["schemas"]["ExpenseClaimCreate"];
type ExpenseClaimLineCreate = components["schemas"]["ExpenseClaimLineCreate"];
type ExpenseClaimResponse = components["schemas"]["ExpenseClaimResponse"];

interface LineDraft {
  key: string;
  expenseCategoryId: string;
  description: string;
  amount: string;
  occurredOn: string;
  attachmentId: string;
  isBillable: boolean;
  customer: CustomerOption | null;
  markupPercent: string;
}

let _key = 0;
const nextKey = () => `cln${++_key}`;

function emptyLine(): LineDraft {
  return {
    key: nextKey(),
    expenseCategoryId: "",
    description: "",
    amount: "",
    occurredOn: new Date().toISOString().slice(0, 10),
    attachmentId: "",
    isBillable: false,
    customer: null,
    markupPercent: "0",
  };
}

export function ExpenseClaimComposerPage() {
  const navigate = useNavigate();

  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>(() => [emptyLine()]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateLine(idx: number, patch: Partial<LineDraft>) {
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
  }

  const total = useMemo(
    () =>
      lines
        .map((l) => {
          const n = Number.parseFloat(l.amount);
          return Number.isFinite(n) ? n : 0;
        })
        .reduce((a, b) => a + b, 0),
    [lines],
  );

  function buildLines(): ExpenseClaimLineCreate[] {
    const out: ExpenseClaimLineCreate[] = [];
    for (const l of lines) {
      if (!l.description.trim() || !l.expenseCategoryId) continue;
      const item: ExpenseClaimLineCreate = {
        description: l.description,
        amount: l.amount || "0",
        expense_category_id: l.expenseCategoryId,
        occurred_on: l.occurredOn,
        is_billable: l.isBillable,
        markup_percent: l.markupPercent || "0",
      };
      if (l.attachmentId.trim()) item.attachment_id = l.attachmentId.trim();
      if (l.isBillable && l.customer) item.customer_id = l.customer.id;
      out.push(item);
    }
    return out;
  }

  async function submit() {
    const built = buildLines();
    if (built.length === 0) {
      setError("Add at least one line with a category and description.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: ExpenseClaimCreate = {
        currency: "USD",
        lines: built,
      };
      if (notes.trim()) body.notes = notes.trim();
      const res = await apiClient.post<ExpenseClaimResponse>(
        "/api/v1/expense-claims",
        body,
      );
      navigate(`/expense-claims/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save claim.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">New expense claim</h1>
      </header>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Header</h2>
        <label className="block text-sm">
          Notes
          <textarea
            className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="claim-notes"
          />
        </label>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Lines</h2>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setLines((p) => [...p, emptyLine()])}
            data-testid="add-line-btn"
          >
            Add line
          </Button>
        </div>
        {lines.map((line, idx) => (
          <div
            key={line.key}
            className="space-y-2 rounded-lg border border-border p-3"
            data-testid={`line-row-${idx}`}
          >
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs">
                Category
                <ExpenseCategoryPicker
                  value={line.expenseCategoryId}
                  onChange={(id) => updateLine(idx, { expenseCategoryId: id })}
                  data-testid={`line-${idx}-category`}
                />
              </label>
              <label className="block text-xs">
                Occurred on
                <Input
                  type="date"
                  value={line.occurredOn}
                  onChange={(e) =>
                    updateLine(idx, { occurredOn: e.target.value })
                  }
                  data-testid={`line-${idx}-occurred-on`}
                />
              </label>
            </div>
            <Input
              value={line.description}
              placeholder="Description"
              onChange={(e) => updateLine(idx, { description: e.target.value })}
              data-testid={`line-${idx}-description`}
            />
            <div className="grid grid-cols-2 gap-2">
              <Input
                type="number"
                step="0.01"
                min={0}
                value={line.amount}
                onChange={(e) => updateLine(idx, { amount: e.target.value })}
                placeholder="Amount"
                data-testid={`line-${idx}-amount`}
              />
              <Input
                value={line.attachmentId}
                onChange={(e) =>
                  updateLine(idx, { attachmentId: e.target.value })
                }
                placeholder="Attachment ID (optional)"
                data-testid={`line-${idx}-attachment-id`}
              />
            </div>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={line.isBillable}
                onChange={(e) =>
                  updateLine(idx, { isBillable: e.target.checked })
                }
                data-testid={`line-${idx}-billable`}
              />
              Billable to customer
            </label>
            {line.isBillable ? (
              <div className="grid grid-cols-2 gap-2">
                <label className="block text-xs">
                  Customer
                  <CustomerPicker
                    value={line.customer}
                    onChange={(c) => updateLine(idx, { customer: c })}
                    data-testid={`line-${idx}-customer-picker`}
                  />
                </label>
                <label className="block text-xs">
                  Markup %
                  <Input
                    type="number"
                    step="0.01"
                    value={line.markupPercent}
                    onChange={(e) =>
                      updateLine(idx, { markupPercent: e.target.value })
                    }
                    data-testid={`line-${idx}-markup`}
                  />
                </label>
              </div>
            ) : null}
            {lines.length > 1 ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setLines((p) => p.filter((_, i) => i !== idx))}
                data-testid={`remove-line-${idx}`}
              >
                Remove
              </Button>
            ) : null}
          </div>
        ))}
        <div className="text-right text-xs" data-testid="claim-total">
          Total: ${total.toFixed(2)}
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void submit()}
          data-testid="claim-save"
        >
          {submitting ? "Saving…" : "Save draft"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/expense-claims")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
