/**
 * `/banking/imports/new` — single-page wizard:
 *   1. pick account
 *   2. pick mapping (or "OFX, no mapping" for .ofx files)
 *   3. choose file
 *   4. submit, show run summary inline
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { BankAccountPicker } from "@/components/banking/BankAccountPicker";
import { Button } from "@/components/ui/Button";

type Mapping = components["schemas"]["BankImportMappingResponse"];
type Run = components["schemas"]["BankImportRunResponse"];

export function ImportWizardPage() {
  const navigate = useNavigate();

  const [accountId, setAccountId] = useState("");
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [mappingId, setMappingId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);

  useEffect(() => {
    if (!accountId) {
      setMappings([]);
      setMappingId("");
      return;
    }
    let cancelled = false;
    api
      .get("/api/v1/bank-import-mappings")
      .then((res) => {
        if (cancelled) return;
        const all = res.data.items;
        const forAccount = all.filter(
          (m) => m.account_id === accountId && m.is_active,
        );
        setMappings(forAccount);
      })
      .catch(() => {
        if (!cancelled) setMappings([]);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  async function submit() {
    if (!accountId) {
      setError("Pick an account.");
      return;
    }
    if (!file) {
      setError("Pick a file.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setRun(null);
    try {
      const fd = new FormData();
      fd.append("account_id", accountId);
      if (mappingId) fd.append("mapping_id", mappingId);
      fd.append("file", file);
      const res = await apiClient.post<Run>("/api/v1/bank-imports", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setRun(res.data);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Import failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Import bank statement</h1>
      </header>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <label className="block text-sm">
          1. Account
          <BankAccountPicker
            value={accountId}
            onChange={setAccountId}
            data-testid="wizard-account"
          />
        </label>

        <label className="block text-sm">
          2. Mapping
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={mappingId}
            onChange={(e) => setMappingId(e.target.value)}
            disabled={!accountId}
            data-testid="wizard-mapping"
          >
            <option value="">OFX (no mapping)</option>
            {mappings.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.file_kind})
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          3. File
          <input
            type="file"
            accept=".csv,.ofx"
            className="mt-1 block w-full text-sm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            data-testid="wizard-file"
          />
        </label>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {run ? (
        <div
          className="space-y-1 rounded-lg border border-border bg-accent/30 p-4 text-sm"
          data-testid="wizard-result"
        >
          <h2 className="text-sm font-semibold">Import complete</h2>
          <p>Filename: {run.filename}</p>
          <p>
            Rows {run.row_count} · Inserted {run.inserted_count} · Duplicates{" "}
            {run.duplicate_count} · Errors {run.error_count}
          </p>
        </div>
      ) : null}

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void submit()}
          data-testid="wizard-submit"
        >
          {submitting ? "Importing…" : "Import"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/banking/imports")}
        >
          {run ? "Back to imports" : "Cancel"}
        </Button>
      </div>
    </section>
  );
}
