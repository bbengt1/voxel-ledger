import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";

type Status = components["schemas"]["QuickBooksStatusResponse"];

const HEALTH_LABEL: Record<string, string> = {
  ok: "Healthy",
  access_expired: "Access token expired (auto-refreshes)",
  reconnect_required: "Reconnect required",
};

function formatExpiry(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export function QuickBooksPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const banner = searchParams.get("connected")
    ? { kind: "ok" as const, text: "QuickBooks connected." }
    : searchParams.get("error")
      ? { kind: "error" as const, text: `Connection failed: ${searchParams.get("error")}` }
      : null;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/admin/quickbooks/status");
      setStatus(res.data);
    } catch {
      setError("Failed to load QuickBooks status.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Clear the ?connected/?error query once shown so a refresh doesn't repeat it.
  useEffect(() => {
    if (banner) {
      const next = new URLSearchParams(searchParams);
      next.delete("connected");
      next.delete("error");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/admin/quickbooks/connect");
      window.location.href = res.data.authorization_url;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data
        ?.detail;
      setError(detail ?? "Could not start the QuickBooks connection. Check QBO_* config.");
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect QuickBooks? This revokes the stored tokens.")) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/v1/admin/quickbooks/disconnect");
      await load();
    } catch {
      setError("Failed to disconnect.");
    } finally {
      setBusy(false);
    }
  }

  async function setEnabled(enabled: boolean) {
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("/api/v1/admin/quickbooks/enabled", { enabled });
      setStatus(res.data);
    } catch {
      setError("Failed to update the sync toggle.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="QuickBooks Online"
        actions={
          status?.connected ? (
            <Button variant="outline" onClick={disconnect} disabled={busy}>
              Disconnect
            </Button>
          ) : (
            <Button onClick={connect} disabled={busy}>
              Connect to QuickBooks
            </Button>
          )
        }
      />

      {banner ? (
        <div
          role="status"
          className={
            banner.kind === "ok"
              ? "rounded border border-green-600 bg-green-50 p-3 text-sm text-green-800"
              : "rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
          }
        >
          {banner.text}
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          data-testid="quickbooks-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : status ? (
        <div className="flex flex-col gap-6">
          <dl className="grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
            <Field label="Connection">
              {status.connected ? (
                <span className="font-medium text-green-700">Connected</span>
              ) : (
                <span className="text-muted-foreground">Not connected</span>
              )}
            </Field>
            <Field label="Environment">
              <span className="capitalize">{status.environment}</span>
            </Field>
            <Field label="Company (realm) ID">{status.realm_id ?? "—"}</Field>
            <Field label="Token health">
              {status.token_health
                ? (HEALTH_LABEL[status.token_health] ?? status.token_health)
                : "—"}
            </Field>
            <Field label="Access token expires">
              {formatExpiry(status.access_token_expires_at)}
            </Field>
            <Field label="Refresh token expires">
              {formatExpiry(status.refresh_token_expires_at)}
            </Field>
          </dl>

          <div className="flex items-start gap-3 border-t pt-4">
            <input
              id="quickbooks-enabled"
              type="checkbox"
              className="mt-1"
              checked={status.enabled}
              disabled={busy || !status.connected}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <label htmlFor="quickbooks-enabled" className="text-sm">
              <span className="font-medium">Enable accounting sync</span>
              <span className="block text-muted-foreground">
                When on, accounting postings are pushed to QuickBooks. Has no effect until
                the sync worker ships (Phase 3). Requires an active connection.
              </span>
            </label>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}
