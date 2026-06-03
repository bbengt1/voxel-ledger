/**
 * `/settings/webhooks` — Outbound webhook subscriptions + delivery
 * history (Phase 11.5, #197). Backed by Phase 11.1 (#193).
 */
import { useCallback, useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { Input } from "@/components/ui/Input";

type Subscription = components["schemas"]["WebhookSubscriptionRead"];
type SubscriptionCreated = components["schemas"]["WebhookSubscriptionCreated"];
type Delivery = components["schemas"]["WebhookDeliveryRead"];

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  delivered: "Delivered",
  failed: "Failed",
  dead_letter: "Dead letter",
};

function SecretBanner({
  secret,
  onDismiss,
}: {
  secret: string;
  onDismiss: () => void;
}) {
  return (
    <div
      data-testid="webhook-secret-banner"
      className="rounded border border-yellow-400 bg-yellow-50 p-3 text-sm"
    >
      <div className="font-medium">Secret (copy now — won't be shown again):</div>
      <div className="flex items-center gap-2 pt-1">
        <code className="flex-1 rounded bg-white px-2 py-1 font-mono text-xs break-all">
          {secret}
        </code>
        <Button
          type="button"
          variant="outline"
          onClick={() => navigator.clipboard?.writeText(secret)}
        >
          Copy
        </Button>
        <Button type="button" variant="outline" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}

function NewSubscriptionForm({
  onCreated,
}: {
  onCreated: (sub: SubscriptionCreated) => void;
}) {
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [types, setTypes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const eventTypes = types
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const resp = await api.post(
        "/api/v1/webhooks/subscriptions",
        { name, target_url: target, event_types: eventTypes, is_active: true },
      );
      onCreated(resp.data as SubscriptionCreated);
      setName("");
      setTarget("");
      setTypes("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      data-testid="webhook-new-form"
      className="space-y-2 rounded border border-border p-3"
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Input
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Input
          placeholder="https://example.com/webhook"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          required
        />
        <Input
          placeholder="event types (comma-separated, * for all)"
          value={types}
          onChange={(e) => setTypes(e.target.value)}
        />
      </div>
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={pending}>
          {pending ? "Creating..." : "Create subscription"}
        </Button>
        {error ? <span className="text-sm text-red-600">{error}</span> : null}
      </div>
    </form>
  );
}

function SubscriptionsTab() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const resp = await api.get("/api/v1/webhooks/subscriptions");
      setSubs(resp.data as Subscription[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const columns: DataTableColumn<Subscription>[] = [
    { key: "name", header: "Name", isPrimary: true, cell: (s) => s.name },
    {
      key: "url",
      header: "URL",
      cellClassName: "font-mono text-xs",
      cell: (s) => s.target_url,
    },
    {
      key: "events",
      header: "Events",
      cell: (s) => (s.event_types || []).join(", "),
    },
    { key: "active", header: "Active", cell: (s) => (s.is_active ? "yes" : "no") },
  ];

  return (
    <div className="space-y-3">
      {createdSecret ? (
        <SecretBanner
          secret={createdSecret}
          onDismiss={() => setCreatedSecret(null)}
        />
      ) : null}
      <NewSubscriptionForm
        onCreated={(sub) => {
          setCreatedSecret(sub.secret);
          void refresh();
        }}
      />
      {error ? <div className="text-sm text-red-600">{error}</div> : null}
      <DataTable
        columns={columns}
        rows={subs}
        getRowKey={(s) => s.id}
        emptyMessage="No subscriptions yet."
        minWidthClassName="min-w-[560px]"
      />
    </div>
  );
}

function DeliveriesTab() {
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const resp = await api.get("/api/v1/webhooks/deliveries");
      setDeliveries(resp.data as Delivery[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function replay(id: string) {
    await apiClient.post(`/api/v1/webhooks/deliveries/${id}/replay`);
    await refresh();
  }

  const columns: DataTableColumn<Delivery>[] = [
    {
      key: "event",
      header: "Event",
      isPrimary: true,
      cellClassName: "font-mono text-xs",
      cell: (d) => d.event_type,
    },
    {
      key: "status",
      header: "Status",
      cell: (d) => STATUS_LABEL[d.last_status] ?? d.last_status,
    },
    {
      key: "attempts",
      header: "Attempts",
      align: "right",
      cellClassName: "tabular-nums",
      cell: (d) => d.attempt_count,
    },
    {
      key: "next",
      header: "Next",
      cellClassName: "font-mono text-xs",
      cell: (d) => d.next_attempt_at,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cardFullWidth: true,
      cell: (d) => (
        <Button
          type="button"
          variant="outline"
          data-testid={`webhook-replay-${d.id}`}
          onClick={() => void replay(d.id)}
        >
          Replay
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-3">
      {error ? <div className="text-sm text-red-600">{error}</div> : null}
      <DataTable
        columns={columns}
        rows={deliveries}
        getRowKey={(d) => d.id}
        emptyMessage="No deliveries yet."
        minWidthClassName="min-w-[640px]"
      />
    </div>
  );
}

export function WebhooksSettingsPage() {
  const [tab, setTab] = useState<"subs" | "deliveries">("subs");
  return (
    <div className="space-y-4 p-6">
      <h1 className="text-xl font-semibold">Webhooks</h1>
      <div className="flex gap-2 border-b border-border">
        <button
          type="button"
          data-testid="webhook-tab-subs"
          onClick={() => setTab("subs")}
          className={`px-3 py-2 text-sm ${tab === "subs" ? "border-b-2 border-primary" : ""}`}
        >
          Subscriptions
        </button>
        <button
          type="button"
          data-testid="webhook-tab-deliveries"
          onClick={() => setTab("deliveries")}
          className={`px-3 py-2 text-sm ${tab === "deliveries" ? "border-b-2 border-primary" : ""}`}
        >
          Deliveries
        </button>
      </div>
      {tab === "subs" ? <SubscriptionsTab /> : <DeliveriesTab />}
    </div>
  );
}
