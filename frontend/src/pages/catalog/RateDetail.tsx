import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type RateResponse = components["schemas"]["RateResponse"];

const KIND_LABELS: Record<RateResponse["kind"], string> = {
  labor: "Labor",
  machine: "Machine",
  overhead: "Overhead",
};

export function RateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";

  const [rate, setRate] = useState<RateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [printerId, setPrinterId] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  function syncForm(r: RateResponse) {
    setName(r.name);
    setValue(r.value);
    setPrinterId(r.applies_to_printer_id ?? "");
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<RateResponse>(`/api/v1/rates/${id}`)
      .then((res) => {
        if (cancelled) return;
        setRate(res.data);
        syncForm(res.data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load rate.";
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
      const body: Record<string, unknown> = { name, value };
      body["applies_to_printer_id"] = printerId.trim() || null;
      const res = await apiClient.patch<RateResponse>(
        `/api/v1/rates/${id}`,
        body,
      );
      setRate(res.data);
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

  async function doSetDefault() {
    if (!id) return;
    try {
      const res = await apiClient.post<RateResponse>(
        `/api/v1/rates/${id}/set-default`,
      );
      setRate(res.data);
      setSaveMsg("Set as default.");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not set default.";
      setSaveMsg(detail);
    }
  }

  async function doArchive() {
    if (!id) return;
    try {
      const res = await apiClient.post<RateResponse>(
        `/api/v1/rates/${id}/archive`,
      );
      setRate(res.data);
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
      const res = await apiClient.post<RateResponse>(
        `/api/v1/rates/${id}/unarchive`,
      );
      setRate(res.data);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not unarchive.";
      setSaveMsg(detail);
    }
  }

  if (loading) return <p>Loading…</p>;
  if (error || !rate)
    return (
      <div role="alert" className="text-destructive">
        {error ?? "Rate not found."}
      </div>
    );

  return (
    <section className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{rate.name}</h1>
        <p className="text-sm text-muted-foreground">
          {KIND_LABELS[rate.kind]} ·{" "}
          {rate.is_default_for_kind ? "Default" : "Not default"} ·{" "}
          {rate.is_archived ? "Archived" : "Active"}
        </p>
      </header>

      {isOwner ? (
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
            Value
            <Input
              className="mt-1"
              inputMode="decimal"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </label>
          {rate.kind === "machine" ? (
            <label className="block text-sm">
              Applies to printer ID
              <Input
                className="mt-1"
                placeholder="(Phase 5 will replace this with a dropdown)"
                value={printerId}
                onChange={(e) => setPrinterId(e.target.value)}
              />
            </label>
          ) : null}
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} data-testid="save-btn">
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate("/catalog/rates")}
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

      {isOwner && !rate.is_archived && !rate.is_default_for_kind ? (
        <section className="space-y-2 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Default</h2>
          <Button onClick={doSetDefault} data-testid="set-default-btn">
            Set as default
          </Button>
        </section>
      ) : null}

      {isOwner ? (
        <section className="space-y-2 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Lifecycle</h2>
          <div className="flex gap-2">
            {rate.is_archived ? (
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
