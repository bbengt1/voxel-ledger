import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type PrinterResponse = components["schemas"]["PrinterResponse"];
type CameraResponse = components["schemas"]["CameraResponse"];

const CAN_WRITE_ROLES = ["owner", "production"] as const;

const STATUS_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "decommissioned", label: "Decommissioned" },
];

function statusBadgeClass(status: string): string {
  switch (status) {
    case "active":
      return "bg-green-100 text-green-800";
    case "inactive":
      return "bg-amber-100 text-amber-800";
    case "decommissioned":
      return "bg-zinc-200 text-zinc-700";
    default:
      return "bg-muted text-muted-foreground";
  }
}

const CAMERA_KIND_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "go2rtc", label: "go2rtc (snapshot proxy supported)" },
  { value: "wyze", label: "Wyze (not yet proxied)" },
  { value: "rtsp", label: "RTSP (not yet proxied)" },
  { value: "other", label: "Other" },
];

export function PrinterDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const [printer, setPrinter] = useState<PrinterResponse | null>(null);
  const [camera, setCamera] = useState<CameraResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Printer editable fields.
  const [name, setName] = useState("");
  const [moonrakerUrl, setMoonrakerUrl] = useState("");
  const [moonrakerApiKey, setMoonrakerApiKey] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<string>("active");

  // Cost / power fields (#249).
  const [powerDrawWatts, setPowerDrawWatts] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");
  const [salvageValue, setSalvageValue] = useState("");
  const [lifespanYears, setLifespanYears] = useState("");
  const [annualPrintHours, setAnnualPrintHours] = useState("");
  const [preheatMinutes, setPreheatMinutes] = useState("");
  const [preheatPowerWatts, setPreheatPowerWatts] = useState("");

  // Camera editable fields.
  const [camKind, setCamKind] = useState<string>("go2rtc");
  const [camUrl, setCamUrl] = useState("");
  const [camUsername, setCamUsername] = useState("");
  const [camPassword, setCamPassword] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  function syncFromPrinter(p: PrinterResponse) {
    setName(p.name);
    setMoonrakerUrl(p.moonraker_url ?? "");
    setMoonrakerApiKey("");
    setNotes(p.notes ?? "");
    setStatus(p.status ?? "active");
    setPowerDrawWatts(p.power_draw_watts != null ? String(p.power_draw_watts) : "");
    setPurchasePrice(p.purchase_price != null ? String(p.purchase_price) : "");
    setSalvageValue(p.salvage_value != null ? String(p.salvage_value) : "");
    setLifespanYears(p.lifespan_years != null ? String(p.lifespan_years) : "");
    setAnnualPrintHours(
      p.annual_print_hours != null ? String(p.annual_print_hours) : "",
    );
    setPreheatMinutes(
      p.preheat_minutes != null ? String(p.preheat_minutes) : "",
    );
    setPreheatPowerWatts(
      p.preheat_power_watts != null ? String(p.preheat_power_watts) : "",
    );
  }

  function syncFromCamera(c: CameraResponse | null) {
    if (!c) {
      setCamKind("go2rtc");
      setCamUrl("");
      setCamUsername("");
      setCamPassword("");
      return;
    }
    setCamKind(c.kind);
    setCamUrl(c.snapshot_url);
    setCamUsername(c.username ?? "");
    setCamPassword("");
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      apiClient.get<PrinterResponse>(`/api/v1/printers/${id}`),
      apiClient
        .get<CameraResponse>(`/api/v1/printers/${id}/cameras`)
        .catch(() => null),
    ])
      .then(([pr, cam]) => {
        if (cancelled) return;
        setPrinter(pr.data);
        syncFromPrinter(pr.data);
        const c = cam ? cam.data : null;
        setCamera(c);
        syncFromCamera(c);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load printer.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function savePrinter() {
    if (!id) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const body: Record<string, unknown> = { name, notes: notes || null };
      body["status"] = status;
      body["moonraker_url"] = moonrakerUrl.trim() || null;
      if (moonrakerApiKey.trim()) body["moonraker_api_key"] = moonrakerApiKey;
      const intOrNull = (s: string) => (s.trim() === "" ? null : Number(s));
      const decOrNull = (s: string) => (s.trim() === "" ? null : s.trim());
      body["power_draw_watts"] = intOrNull(powerDrawWatts);
      body["purchase_price"] = decOrNull(purchasePrice);
      body["salvage_value"] = decOrNull(salvageValue);
      body["lifespan_years"] = intOrNull(lifespanYears);
      body["annual_print_hours"] = intOrNull(annualPrintHours);
      body["preheat_minutes"] = intOrNull(preheatMinutes);
      body["preheat_power_watts"] = intOrNull(preheatPowerWatts);
      const r = await apiClient.patch<PrinterResponse>(
        `/api/v1/printers/${id}`,
        body,
      );
      setPrinter(r.data);
      syncFromPrinter(r.data);
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

  async function saveCamera() {
    if (!id) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const body: Record<string, unknown> = {
        kind: camKind,
        snapshot_url: camUrl,
        is_active: true,
      };
      if (camUsername.trim()) body["username"] = camUsername.trim();
      if (camPassword.trim()) body["password_secret"] = camPassword;
      const r = await apiClient.post<CameraResponse>(
        `/api/v1/printers/${id}/cameras`,
        body,
      );
      setCamera(r.data);
      syncFromCamera(r.data);
      setSaveMsg("Camera saved.");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Camera save failed.";
      setSaveMsg(typeof detail === "string" ? detail : "Camera save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteCamera() {
    if (!id) return;
    setSaving(true);
    try {
      await apiClient.delete(`/api/v1/printers/${id}/cameras`);
      setCamera(null);
      syncFromCamera(null);
      setSaveMsg("Camera removed.");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not remove camera.";
      setSaveMsg(typeof detail === "string" ? detail : "Could not remove camera.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleArchive() {
    if (!printer) return;
    setSaving(true);
    try {
      const path = printer.is_archived ? "unarchive" : "archive";
      const r = await apiClient.post<PrinterResponse>(
        `/api/v1/printers/${printer.id}/${path}`,
      );
      setPrinter(r.data);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p>Loading...</p>;
  if (error)
    return (
      <p role="alert" className="text-destructive">
        {error}
      </p>
    );
  if (!printer) return <p>Printer not found.</p>;

  return (
    <section className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            {printer.name}
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadgeClass(printer.status)}`}
              data-testid="status-chip"
            >
              {printer.status}
            </span>
          </h1>
          <p className="text-sm text-muted-foreground">
            {printer.slug} · {printer.printer_type} ·{" "}
            {printer.is_archived ? "Archived" : "Active row"}
          </p>
        </div>
        <div className="flex gap-2">
          {isOwner ? (
            <Button variant="outline" onClick={toggleArchive} disabled={saving}>
              {printer.is_archived ? "Unarchive" : "Archive"}
            </Button>
          ) : null}
          <Button
            variant="outline"
            onClick={() => navigate("/production/printers")}
          >
            Back
          </Button>
        </div>
      </header>

      {saveMsg ? (
        <p
          data-testid="save-msg"
          className="rounded border border-border bg-muted/30 p-2 text-sm"
        >
          {saveMsg}
        </p>
      ) : null}

      <fieldset
        className="space-y-3 rounded-md border border-border p-4"
        disabled={!canWrite || saving}
      >
        <legend className="px-1 text-sm font-medium">Printer</legend>
        <label className="block text-sm">
          Name
          <Input
            className="mt-1"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Status
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            data-testid="status-select"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Moonraker URL
          <Input
            className="mt-1"
            value={moonrakerUrl}
            onChange={(e) => setMoonrakerUrl(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Moonraker API key{" "}
          <span className="text-muted-foreground">
            {printer.moonraker_api_key_set
              ? "(configured — leave blank to keep)"
              : "(not set)"}
          </span>
          <Input
            className="mt-1"
            type="password"
            value={moonrakerApiKey}
            onChange={(e) => setMoonrakerApiKey(e.target.value)}
            placeholder="New value (write-only)"
          />
        </label>
        <label className="block text-sm">
          Notes
          <textarea
            className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
          />
        </label>
        {canWrite ? (
          <Button type="button" onClick={savePrinter} disabled={saving}>
            Save printer
          </Button>
        ) : null}
      </fieldset>

      <fieldset
        className="space-y-3 rounded-md border border-border p-4"
        disabled={!canWrite || saving}
      >
        <legend className="px-1 text-sm font-medium">Cost & power</legend>
        <p className="text-xs text-muted-foreground">
          When the full set (power draw, purchase price, salvage, lifespan
          years, annual hours) is filled in, the cost engine derives this
          printer&apos;s per-hour cost from electricity + depreciation instead
          of the flat machine-rate fallback.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Avg power draw (W)
            <Input
              className="mt-1"
              inputMode="decimal"
              value={powerDrawWatts}
              onChange={(e) => setPowerDrawWatts(e.target.value)}
              data-testid="power-draw-watts"
            />
          </label>
          <label className="block text-sm">
            Purchase price
            <Input
              className="mt-1"
              inputMode="decimal"
              value={purchasePrice}
              onChange={(e) => setPurchasePrice(e.target.value)}
              data-testid="purchase-price"
            />
          </label>
          <label className="block text-sm">
            Salvage value
            <Input
              className="mt-1"
              inputMode="decimal"
              value={salvageValue}
              onChange={(e) => setSalvageValue(e.target.value)}
              data-testid="salvage-value"
            />
          </label>
          <label className="block text-sm">
            Lifespan (years)
            <Input
              className="mt-1"
              inputMode="decimal"
              value={lifespanYears}
              onChange={(e) => setLifespanYears(e.target.value)}
              data-testid="lifespan-years"
            />
          </label>
          <label className="block text-sm">
            Annual print hours
            <Input
              className="mt-1"
              inputMode="decimal"
              value={annualPrintHours}
              onChange={(e) => setAnnualPrintHours(e.target.value)}
              data-testid="annual-print-hours"
            />
          </label>
          <label className="block text-sm">
            Preheat minutes
            <Input
              className="mt-1"
              inputMode="decimal"
              value={preheatMinutes}
              onChange={(e) => setPreheatMinutes(e.target.value)}
              data-testid="preheat-minutes"
            />
          </label>
          <label className="block text-sm">
            Preheat power (W)
            <Input
              className="mt-1"
              inputMode="decimal"
              value={preheatPowerWatts}
              onChange={(e) => setPreheatPowerWatts(e.target.value)}
              data-testid="preheat-power-watts"
            />
          </label>
        </div>
        {canWrite ? (
          <Button type="button" onClick={savePrinter} disabled={saving}>
            Save cost & power
          </Button>
        ) : null}
      </fieldset>

      <fieldset
        className="space-y-3 rounded-md border border-border p-4"
        disabled={!canWrite || saving}
      >
        <legend className="px-1 text-sm font-medium">Camera</legend>

        {camera ? (
          <>
            <p className="text-xs text-muted-foreground">
              Configured · password{" "}
              {camera.password_secret_set ? "stored" : "not set"}
            </p>
            <img
              alt="Camera snapshot"
              src={`/api/v1/printers/${printer.id}/cameras/snapshot.jpg`}
              className="max-h-64 rounded border border-border"
              data-testid="camera-snapshot"
            />
          </>
        ) : (
          <p className="text-xs text-muted-foreground">No camera configured.</p>
        )}

        <label className="block text-sm">
          Kind
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={camKind}
            onChange={(e) => setCamKind(e.target.value)}
          >
            {CAMERA_KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Snapshot URL
          <Input
            className="mt-1"
            value={camUrl}
            onChange={(e) => setCamUrl(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Username
          <Input
            className="mt-1"
            value={camUsername}
            onChange={(e) => setCamUsername(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Password{" "}
          {camera ? (
            <span className="text-muted-foreground">
              {camera.password_secret_set
                ? "(stored — leave blank to keep)"
                : "(not set)"}
            </span>
          ) : null}
          <Input
            className="mt-1"
            type="password"
            value={camPassword}
            onChange={(e) => setCamPassword(e.target.value)}
            placeholder="(write-only)"
          />
        </label>
        {canWrite ? (
          <div className="flex gap-2">
            <Button type="button" onClick={saveCamera} disabled={saving}>
              {camera ? "Update camera" : "Configure camera"}
            </Button>
            {camera ? (
              <Button
                type="button"
                variant="outline"
                onClick={deleteCamera}
                disabled={saving}
              >
                Remove camera
              </Button>
            ) : null}
          </div>
        ) : null}
      </fieldset>
    </section>
  );
}
