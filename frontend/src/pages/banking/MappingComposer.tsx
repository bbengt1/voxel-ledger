/**
 * `/banking/mappings/new` — author a CSV / OFX mapping config. Includes a
 * live-preview pane: paste a few rows from your file, see how the column
 * map + date format + amount sign interpret them before saving.
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { BankAccountPicker } from "@/components/banking/BankAccountPicker";
import { parseCsvPreview } from "@/components/banking/CsvPreviewParser";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type MappingCreate = components["schemas"]["BankImportMappingCreate"];
type MappingResponse = components["schemas"]["BankImportMappingResponse"];

const FILE_KINDS = ["csv", "ofx"] as const;
const AMOUNT_SIGNS = [
  "signed_amount",
  "debit_credit_columns",
  "inflow_outflow",
] as const;
const DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"] as const;

const COLUMN_KEYS = [
  "date",
  "description",
  "amount",
  "debit",
  "credit",
  "balance",
  "memo",
] as const;

export function MappingComposerPage() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [accountId, setAccountId] = useState("");
  const [fileKind, setFileKind] = useState<(typeof FILE_KINDS)[number]>("csv");
  const [delimiter, setDelimiter] = useState(",");
  const [hasHeader, setHasHeader] = useState(true);
  const [encoding, setEncoding] = useState("utf-8");
  const [dateFormat, setDateFormat] =
    useState<(typeof DATE_FORMATS)[number]>("%Y-%m-%d");
  const [amountSign, setAmountSign] =
    useState<(typeof AMOUNT_SIGNS)[number]>("signed_amount");
  const [columnMap, setColumnMap] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");

  const [preview, setPreview] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const previewRows = useMemo(() => {
    if (fileKind !== "csv" || !preview.trim()) return [];
    return parseCsvPreview(preview, {
      column_map: columnMap,
      delimiter,
      has_header: hasHeader,
      date_format: dateFormat,
      amount_sign: amountSign,
    });
  }, [preview, fileKind, columnMap, delimiter, hasHeader, dateFormat, amountSign]);

  function updateColumn(key: string, value: string) {
    setColumnMap((prev) => {
      const next = { ...prev };
      if (value.trim()) next[key] = value.trim();
      else delete next[key];
      return next;
    });
  }

  async function submit() {
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (!accountId) {
      setError("Pick an account.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: MappingCreate = {
        name: name.trim(),
        account_id: accountId,
        file_kind: fileKind,
        amount_sign: amountSign,
        delimiter,
        encoding,
        has_header: hasHeader,
        column_map: columnMap,
      };
      if (dateFormat) body.date_format = dateFormat;
      if (notes.trim()) body.notes = notes.trim();
      const res = await apiClient.post<MappingResponse>(
        "/api/v1/bank-import-mappings",
        body,
      );
      navigate(`/banking/mappings`, { state: { created: res.data.id } });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save mapping.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">New bank import mapping</h1>
      </header>

      <div className="grid grid-cols-2 gap-3 rounded-lg border border-border p-4">
        <label className="block text-sm">
          Name
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="mapping-name"
          />
        </label>
        <label className="block text-sm">
          Account
          <BankAccountPicker
            value={accountId}
            onChange={setAccountId}
            data-testid="mapping-account"
          />
        </label>
        <fieldset className="text-sm">
          <legend className="font-medium">File kind</legend>
          {FILE_KINDS.map((k) => (
            <label key={k} className="mr-3 inline-flex items-center gap-1">
              <input
                type="radio"
                name="file-kind"
                value={k}
                checked={fileKind === k}
                onChange={() => setFileKind(k)}
                data-testid={`file-kind-${k}`}
              />
              {k.toUpperCase()}
            </label>
          ))}
        </fieldset>
        <label className="block text-sm">
          Delimiter
          <Input
            value={delimiter}
            onChange={(e) => setDelimiter(e.target.value)}
            data-testid="mapping-delimiter"
            disabled={fileKind !== "csv"}
          />
        </label>
        <label className="block text-sm">
          Encoding
          <Input
            value={encoding}
            onChange={(e) => setEncoding(e.target.value)}
            data-testid="mapping-encoding"
          />
        </label>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={hasHeader}
            onChange={(e) => setHasHeader(e.target.checked)}
            data-testid="mapping-has-header"
            disabled={fileKind !== "csv"}
          />
          Has header row
        </label>
        <label className="block text-sm">
          Date format
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={dateFormat}
            onChange={(e) =>
              setDateFormat(e.target.value as (typeof DATE_FORMATS)[number])
            }
            data-testid="mapping-date-format"
          >
            {DATE_FORMATS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="col-span-2 text-sm">
          <legend className="font-medium">Amount sign</legend>
          {AMOUNT_SIGNS.map((s) => (
            <label key={s} className="mr-3 inline-flex items-center gap-1">
              <input
                type="radio"
                name="amount-sign"
                value={s}
                checked={amountSign === s}
                onChange={() => setAmountSign(s)}
                data-testid={`amount-sign-${s}`}
              />
              {s}
            </label>
          ))}
        </fieldset>
      </div>

      {fileKind === "csv" ? (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Column map</h2>
          <p className="text-xs text-muted-foreground">
            Map each logical field to the matching header in your CSV.
          </p>
          <div className="grid grid-cols-2 gap-3">
            {COLUMN_KEYS.map((key) => (
              <label key={key} className="block text-sm">
                {key}
                <Input
                  value={columnMap[key] ?? ""}
                  onChange={(e) => updateColumn(key, e.target.value)}
                  data-testid={`col-${key}`}
                />
              </label>
            ))}
          </div>
        </div>
      ) : null}

      {fileKind === "csv" ? (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Live preview</h2>
          <p className="text-xs text-muted-foreground">
            Paste a header row + a few data rows to see how the config parses them.
          </p>
          <textarea
            rows={5}
            className="w-full rounded-md border border-input bg-background p-2 font-mono text-xs"
            value={preview}
            onChange={(e) => setPreview(e.target.value)}
            data-testid="mapping-preview-input"
          />
          {previewRows.length > 0 ? (
            <table
              className="w-full text-xs"
              data-testid="mapping-preview-table"
            >
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 pr-2">Date</th>
                  <th className="py-1 pr-2">Description</th>
                  <th className="py-1 pr-2 text-right">Amount</th>
                  <th className="py-1 pr-2">Memo</th>
                </tr>
              </thead>
              <tbody>
                {previewRows.map((r, i) => (
                  <tr
                    key={i}
                    className="border-b border-border/30"
                    data-testid={`preview-row-${i}`}
                  >
                    <td className="py-1 pr-2 font-mono">{r.date}</td>
                    <td className="py-1 pr-2">{r.description}</td>
                    <td className="py-1 pr-2 text-right font-mono">
                      {r.amount}
                    </td>
                    <td className="py-1 pr-2">{r.memo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      ) : null}

      <label className="block text-sm">
        Notes
        <textarea
          rows={2}
          className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          data-testid="mapping-notes"
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
          data-testid="save-mapping"
        >
          {submitting ? "Saving…" : "Save mapping"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/banking/mappings")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
