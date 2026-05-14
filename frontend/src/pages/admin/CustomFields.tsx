import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type EntityType = "material" | "supply" | "rate" | "product";
type FieldType = "string" | "number" | "boolean" | "date" | "select";

interface CustomFieldRow {
  id: string;
  entity_type: string;
  key: string;
  label: string;
  field_type: FieldType;
  required: boolean;
  display_order: number;
  is_archived: boolean;
  options?: { value: string; label: string }[] | null;
}

const ENTITY_TYPES: EntityType[] = ["material", "supply", "rate", "product"];
const FIELD_TYPES: FieldType[] = [
  "string",
  "number",
  "boolean",
  "date",
  "select",
];

export function CustomFieldsPage() {
  const [tab, setTab] = useState<EntityType>("material");
  const [rows, setRows] = useState<CustomFieldRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New-field form state.
  const [newKey, setNewKey] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newType, setNewType] = useState<FieldType>("string");
  const [newRequired, setNewRequired] = useState(false);
  const [newOptions, setNewOptions] = useState<
    { value: string; label: string }[]
  >([]);
  const [submitting, setSubmitting] = useState(false);

  const reload = () => {
    setLoading(true);
    setError(null);
    api
      .get(
        `/api/v1/custom-fields?entity_type=${encodeURIComponent(tab)}&include_archived=true`,
      )
      .then((res) => setRows(res.data.items as CustomFieldRow[]))
      .catch((err: unknown) => {
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load custom fields.";
        setError(typeof msg === "string" ? msg : "Failed to load.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        entity_type: tab,
        key: newKey,
        label: newLabel,
        field_type: newType,
        required: newRequired,
      };
      if (newType === "select") body["options"] = newOptions;
      await api.post("/api/v1/custom-fields", body);
      setNewKey("");
      setNewLabel("");
      setNewRequired(false);
      setNewOptions([]);
      reload();
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to create field.";
      setError(typeof msg === "string" ? msg : "Failed to create.");
    } finally {
      setSubmitting(false);
    }
  };

  const onArchive = async (id: string) => {
    await api.post(`/api/v1/custom-fields/${id}/archive`);
    reload();
  };

  const onUnarchive = async (id: string) => {
    await api.post(`/api/v1/custom-fields/${id}/unarchive`);
    reload();
  };

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Custom fields</h1>
      </header>

      <nav aria-label="Entity tabs" className="flex gap-2 border-b border-border">
        {ENTITY_TYPES.map((et) => (
          <button
            key={et}
            type="button"
            onClick={() => setTab(et)}
            className={`px-3 py-1.5 text-sm border-b-2 ${
              tab === et
                ? "border-foreground font-semibold"
                : "border-transparent text-muted-foreground"
            }`}
          >
            {et}
          </button>
        ))}
      </nav>

      {error && (
        <div role="alert" className="text-sm text-destructive">
          {error}
        </div>
      )}

      <form
        onSubmit={onCreate}
        className="flex flex-col gap-2 rounded-md border border-border p-3"
        aria-label="Add custom field"
      >
        <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
          <label className="flex flex-col gap-1 text-sm">
            <span>key</span>
            <Input
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="supplier_code"
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span>label</span>
            <Input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Supplier Code"
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span>type</span>
            <select
              value={newType}
              onChange={(e) => setNewType(e.target.value as FieldType)}
              className="rounded-md border border-input bg-background px-2 py-1 text-sm"
            >
              {FIELD_TYPES.map((ft) => (
                <option key={ft} value={ft}>
                  {ft}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={newRequired}
              onChange={(e) => setNewRequired(e.target.checked)}
            />
            <span>required</span>
          </label>
        </div>
        {newType === "select" && (
          <div className="flex flex-col gap-2" aria-label="Select options">
            {newOptions.map((opt, i) => (
              <div key={i} className="flex gap-2">
                <Input
                  value={opt.value}
                  onChange={(e) => {
                    const next = [...newOptions];
                    next[i] = { ...opt, value: e.target.value };
                    setNewOptions(next);
                  }}
                  placeholder="value"
                />
                <Input
                  value={opt.label}
                  onChange={(e) => {
                    const next = [...newOptions];
                    next[i] = { ...opt, label: e.target.value };
                    setNewOptions(next);
                  }}
                  placeholder="label"
                />
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() =>
                    setNewOptions(newOptions.filter((_, j) => j !== i))
                  }
                >
                  Remove
                </Button>
              </div>
            ))}
            <Button
              type="button"
              variant="secondary"
              onClick={() =>
                setNewOptions([...newOptions, { value: "", label: "" }])
              }
            >
              Add option
            </Button>
          </div>
        )}
        <div>
          <Button type="submit" disabled={submitting}>
            Add field
          </Button>
        </div>
      </form>

      {loading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left">
              <th className="border-b border-border py-2">key</th>
              <th className="border-b border-border py-2">label</th>
              <th className="border-b border-border py-2">type</th>
              <th className="border-b border-border py-2">required</th>
              <th className="border-b border-border py-2">status</th>
              <th className="border-b border-border py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="border-b border-border py-2 font-mono">
                  {r.key}
                </td>
                <td className="border-b border-border py-2">{r.label}</td>
                <td className="border-b border-border py-2">{r.field_type}</td>
                <td className="border-b border-border py-2">
                  {r.required ? "yes" : "no"}
                </td>
                <td className="border-b border-border py-2">
                  {r.is_archived ? "archived" : "active"}
                </td>
                <td className="border-b border-border py-2 text-right">
                  {r.is_archived ? (
                    <Button
                      variant="secondary"
                      onClick={() => void onUnarchive(r.id)}
                    >
                      Unarchive
                    </Button>
                  ) : (
                    <Button
                      variant="secondary"
                      onClick={() => void onArchive(r.id)}
                    >
                      Archive
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="py-3 text-center text-muted-foreground"
                >
                  No custom fields yet for {tab}.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </section>
  );
}
