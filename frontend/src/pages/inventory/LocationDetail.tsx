import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

const CAN_WRITE_ROLES = ["owner", "production"] as const;

const KIND_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "workshop", label: "Workshop" },
  { value: "finished_goods", label: "Finished goods" },
  { value: "staging", label: "Staging" },
  { value: "customer_pickup", label: "Customer pickup" },
  { value: "consignment", label: "Consignment" },
  { value: "virtual", label: "Virtual" },
];

export function LocationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const [location, setLocation] = useState<InventoryLocationResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [kind, setKind] = useState<string>("workshop");
  const [description, setDescription] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  function syncForm(loc: InventoryLocationResponse) {
    setName(loc.name);
    setCode(loc.code);
    setKind(loc.kind);
    setDescription(loc.description ?? "");
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<InventoryLocationResponse>(`/api/v1/inventory/locations/${id}`)
      .then((res) => {
        if (cancelled) return;
        setLocation(res.data);
        syncForm(res.data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load location.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function save() {
    if (!id) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const body: Record<string, unknown> = { name, code, kind };
      body["description"] = description.trim() || null;
      const res = await apiClient.patch<InventoryLocationResponse>(
        `/api/v1/inventory/locations/${id}`,
        body,
      );
      setLocation(res.data);
      setSaveMsg("Saved.");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Save failed.";
      setSaveMsg(typeof detail === "string" ? detail : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function doArchive() {
    if (!id) return;
    if (!window.confirm("Archive this inventory location?")) return;
    try {
      const res = await apiClient.post<InventoryLocationResponse>(
        `/api/v1/inventory/locations/${id}/archive`,
      );
      setLocation(res.data);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not archive.";
      setSaveMsg(detail);
    }
  }

  async function doUnarchive() {
    if (!id) return;
    try {
      const res = await apiClient.post<InventoryLocationResponse>(
        `/api/v1/inventory/locations/${id}/unarchive`,
      );
      setLocation(res.data);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not unarchive.";
      setSaveMsg(detail);
    }
  }

  if (loading) return <p>Loading…</p>;
  if (error || !location)
    return (
      <div role="alert" className="text-destructive">
        {error ?? "Location not found."}
      </div>
    );

  return (
    <section className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{location.name}</h1>
        <p className="text-sm text-muted-foreground">
          <span data-testid="location-code" className="font-mono">
            {location.code}
          </span>{" "}
          · {location.kind} ·{" "}
          {location.is_archived ? "Archived" : "Active"}
        </p>
      </header>

      {canWrite ? (
        <fieldset className="space-y-3" data-testid="edit-form">
          <legend className="text-sm font-medium">Profile</legend>
          <label className="block text-sm">
            Name
            <Input
              className="mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Code
            <Input
              className="mt-1"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              maxLength={32}
            />
          </label>
          <label className="block text-sm">
            Kind
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {KIND_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Description
            <textarea
              className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </label>
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} data-testid="save-btn">
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate("/inventory/locations")}
            >
              Back
            </Button>
          </div>
          {saveMsg ? (
            <p role="status" data-testid="save-msg" className="text-sm">
              {saveMsg}
            </p>
          ) : null}
        </fieldset>
      ) : null}

      {isOwner ? (
        <section className="space-y-2 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Lifecycle</h2>
          <div className="flex gap-2">
            {location.is_archived ? (
              <Button onClick={doUnarchive} data-testid="unarchive-btn">
                Unarchive
              </Button>
            ) : (
              <Button
                variant="destructive"
                onClick={doArchive}
                data-testid="archive-btn"
              >
                Archive
              </Button>
            )}
          </div>
        </section>
      ) : null}
    </section>
  );
}
