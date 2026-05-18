/**
 * `/banking/match-rules/new` — author a bank-match rule. Validates regex
 * patterns client-side and requires both contra accounts when the action
 * kind is `post_to_account`.
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { BankAccountPicker } from "@/components/banking/BankAccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type RuleCreate = components["schemas"]["BankMatchRuleCreate"];

const MATCH_KINDS = ["regex", "contains", "exact"] as const;
const MATCH_FIELDS = ["description", "memo"] as const;
const ACTION_KINDS = ["match_existing", "post_to_account", "ignore"] as const;

export function MatchRuleComposerPage() {
  const navigate = useNavigate();

  const [accountId, setAccountId] = useState("");
  const [priority, setPriority] = useState("100");
  const [matchKind, setMatchKind] =
    useState<(typeof MATCH_KINDS)[number]>("contains");
  const [matchField, setMatchField] =
    useState<(typeof MATCH_FIELDS)[number]>("description");
  const [matchValue, setMatchValue] = useState("");
  const [minAmount, setMinAmount] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [actionKind, setActionKind] =
    useState<(typeof ACTION_KINDS)[number]>("ignore");
  const [debitAccountId, setDebitAccountId] = useState("");
  const [creditAccountId, setCreditAccountId] = useState("");
  const [descriptionTemplate, setDescriptionTemplate] = useState("");
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const regexError = useMemo(() => {
    if (matchKind !== "regex" || !matchValue) return null;
    try {
      // Force the JS engine to validate the pattern; bytecode is discarded.
      new RegExp(matchValue);
      return null;
    } catch (e: unknown) {
      return e instanceof Error ? e.message : "Invalid regex";
    }
  }, [matchKind, matchValue]);

  async function submit() {
    if (!matchValue.trim()) {
      setError("Match value is required.");
      return;
    }
    if (regexError) {
      setError(`Regex error: ${regexError}`);
      return;
    }
    if (actionKind === "post_to_account") {
      if (!debitAccountId || !creditAccountId) {
        setError("Post-to-account requires both debit and credit accounts.");
        return;
      }
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: RuleCreate = {
        match_kind: matchKind,
        match_field: matchField,
        match_value: matchValue.trim(),
        action_kind: actionKind,
        priority: Number.parseInt(priority, 10) || 100,
      };
      if (accountId) body.account_id = accountId;
      if (minAmount) body.min_amount = minAmount;
      if (maxAmount) body.max_amount = maxAmount;
      if (actionKind === "post_to_account") {
        body.debit_account_id = debitAccountId;
        body.credit_account_id = creditAccountId;
        if (descriptionTemplate.trim()) {
          body.description_template = descriptionTemplate.trim();
        }
      }
      if (notes.trim()) body.notes = notes.trim();
      await apiClient.post("/api/v1/bank-match-rules", body);
      navigate("/banking/match-rules");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save rule.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">New bank match rule</h1>
      </header>

      <div className="grid grid-cols-2 gap-3 rounded-lg border border-border p-4">
        <label className="block text-sm">
          Account scope (blank = global)
          <BankAccountPicker
            value={accountId}
            onChange={setAccountId}
            data-testid="rule-account"
            placeholder="— Global —"
          />
        </label>
        <label className="block text-sm">
          Priority
          <Input
            type="number"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            data-testid="rule-priority"
          />
        </label>

        <fieldset className="text-sm">
          <legend className="font-medium">Match kind</legend>
          {MATCH_KINDS.map((k) => (
            <label key={k} className="mr-3 inline-flex items-center gap-1">
              <input
                type="radio"
                name="match-kind"
                value={k}
                checked={matchKind === k}
                onChange={() => setMatchKind(k)}
                data-testid={`match-kind-${k}`}
              />
              {k}
            </label>
          ))}
        </fieldset>
        <fieldset className="text-sm">
          <legend className="font-medium">Match field</legend>
          {MATCH_FIELDS.map((f) => (
            <label key={f} className="mr-3 inline-flex items-center gap-1">
              <input
                type="radio"
                name="match-field"
                value={f}
                checked={matchField === f}
                onChange={() => setMatchField(f)}
                data-testid={`match-field-${f}`}
              />
              {f}
            </label>
          ))}
        </fieldset>

        <label className="col-span-2 block text-sm">
          Match value
          <Input
            value={matchValue}
            onChange={(e) => setMatchValue(e.target.value)}
            data-testid="rule-match-value"
          />
          {regexError ? (
            <p
              className="mt-1 text-xs text-destructive"
              data-testid="rule-regex-error"
            >
              Regex: {regexError}
            </p>
          ) : null}
        </label>

        <label className="block text-sm">
          Min amount
          <Input
            type="number"
            step="0.01"
            value={minAmount}
            onChange={(e) => setMinAmount(e.target.value)}
            data-testid="rule-min-amount"
          />
        </label>
        <label className="block text-sm">
          Max amount
          <Input
            type="number"
            step="0.01"
            value={maxAmount}
            onChange={(e) => setMaxAmount(e.target.value)}
            data-testid="rule-max-amount"
          />
        </label>

        <fieldset className="col-span-2 text-sm">
          <legend className="font-medium">Action</legend>
          {ACTION_KINDS.map((a) => (
            <label key={a} className="mr-3 inline-flex items-center gap-1">
              <input
                type="radio"
                name="action-kind"
                value={a}
                checked={actionKind === a}
                onChange={() => setActionKind(a)}
                data-testid={`action-kind-${a}`}
              />
              {a}
            </label>
          ))}
        </fieldset>

        {actionKind === "post_to_account" ? (
          <>
            <label className="block text-sm">
              Debit account
              <AccountPicker
                value={debitAccountId}
                onChange={setDebitAccountId}
                data-testid="rule-debit-account"
              />
            </label>
            <label className="block text-sm">
              Credit account
              <AccountPicker
                value={creditAccountId}
                onChange={setCreditAccountId}
                data-testid="rule-credit-account"
              />
            </label>
            <label className="col-span-2 block text-sm">
              Description template
              <Input
                value={descriptionTemplate}
                onChange={(e) => setDescriptionTemplate(e.target.value)}
                data-testid="rule-description-template"
              />
            </label>
          </>
        ) : null}
      </div>

      <label className="block text-sm">
        Notes
        <textarea
          rows={2}
          className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          data-testid="rule-notes"
        />
      </label>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void submit()}
          data-testid="save-rule"
        >
          {submitting ? "Saving…" : "Save rule"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/banking/match-rules")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
