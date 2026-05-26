/**
 * Single printer card for the monitor grid.
 *
 * Polls `/api/v1/printers/{id}/state` every 5s and refreshes the camera
 * snapshot every 2s via the `?t=` cache buster. Honors the 503 warmup
 * contract: when the monitor is starting up, surfaces the `Retry-After`
 * header and a retry button instead of hammering the endpoint.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

type PrinterResponse = components["schemas"]["PrinterResponse"];
type PrinterStateResponse = components["schemas"]["PrinterStateResponse"];

const STATE_POLL_MS = 5_000;
const SNAPSHOT_TICK_MS = 2_000;

const STATE_COLORS: Record<PrinterStateResponse["state"], string> = {
  idle: "bg-muted text-foreground",
  printing: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100",
  paused: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100",
  error: "bg-destructive/20 text-destructive",
  disconnected: "bg-muted text-muted-foreground",
};

function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(iso).toLocaleDateString();
}

function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 0) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function fmtEtaClock(remainingSeconds: number | null | undefined): string {
  if (!remainingSeconds || remainingSeconds < 0) return "—";
  const finish = new Date(Date.now() + remainingSeconds * 1000);
  return finish.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtMeters(mm: number | null | undefined): string {
  if (mm == null) return "—";
  return `${(mm / 1000).toFixed(2)} m`;
}

function fmtFixed(
  value: number | null | undefined,
  digits: number,
  suffix: string,
): string {
  if (value == null) return "—";
  return `${value.toFixed(digits)} ${suffix}`;
}

interface Props {
  printer: PrinterResponse;
}

export function PrinterStateCard({ printer }: Props) {
  const [state, setState] = useState<PrinterStateResponse | null>(null);
  const [warmup, setWarmup] = useState<{ retryAfter: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [hasCamera, setHasCamera] = useState(false);
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);

  const fetchState = useCallback(async () => {
    try {
      const res = await apiClient.get<PrinterStateResponse>(
        `/api/v1/printers/${printer.id}/state`,
      );
      setState(res.data);
      setWarmup(null);
      setError(null);
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; headers?: Record<string, string> } })
        .response;
      if (resp?.status === 503) {
        const ra = Number.parseInt(
          (resp.headers ?? {})["retry-after"] ?? "5",
          10,
        );
        setWarmup({ retryAfter: Number.isFinite(ra) ? ra : 5 });
        return;
      }
      setError("Could not load printer state.");
    }
  }, [printer.id]);

  // Initial + polling fetch.
  useEffect(() => {
    void fetchState();
    const t = window.setInterval(fetchState, STATE_POLL_MS);
    return () => window.clearInterval(t);
  }, [fetchState]);

  // 2s snapshot tick.
  useEffect(() => {
    const t = window.setInterval(
      () => setTick((n) => n + 1),
      SNAPSHOT_TICK_MS,
    );
    return () => window.clearInterval(t);
  }, []);

  // Fetch the gcode thumbnail via axios (so the Authorization header is
  // attached) and turn it into a blob URL the <img> can render. Re-fetch
  // when the current file changes; clear the blob URL on cleanup.
  useEffect(() => {
    const file = state?.current_file;
    const isPrinting = state?.state === "printing";
    if (!isPrinting || !file) {
      setThumbnailUrl(null);
      return;
    }
    let cancelled = false;
    let createdUrl: string | null = null;
    apiClient
      .get<Blob>(`/api/v1/printers/${printer.id}/gcode/thumbnail.png`, {
        responseType: "blob",
      })
      .then((res) => {
        if (cancelled) return;
        const url = URL.createObjectURL(res.data);
        createdUrl = url;
        setThumbnailUrl(url);
      })
      .catch(() => {
        if (!cancelled) setThumbnailUrl(null);
      });
    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [printer.id, state?.current_file, state?.state]);

  // Detect whether a camera is configured (best-effort, one-shot).
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get(`/api/v1/printers/${printer.id}/cameras`)
      .then(() => {
        if (!cancelled) setHasCamera(true);
      })
      .catch(() => {
        if (!cancelled) setHasCamera(false);
      });
    return () => {
      cancelled = true;
    };
  }, [printer.id]);

  return (
    <article
      data-testid={`printer-card-${printer.id}`}
      className="flex flex-col gap-2 rounded-lg border border-border bg-background p-3 shadow-sm"
    >
      <header className="flex items-center justify-between gap-2">
        <Link
          to={`/production/printers/${printer.id}`}
          className="text-sm font-semibold hover:underline"
        >
          {printer.name}
        </Link>
        <div className="flex items-center gap-2">
          {state ? (
            <span
              className={cn(
                "rounded px-2 py-0.5 text-xs font-medium",
                STATE_COLORS[state.state],
              )}
              data-testid={`printer-card-state-${printer.id}`}
            >
              {state.state}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">…</span>
          )}
          <Button
            size="sm"
            variant="outline"
            asChild
            data-testid={`printer-card-edit-${printer.id}`}
          >
            <Link to={`/production/printers/${printer.id}`}>Edit</Link>
          </Button>
        </div>
      </header>

      <div className="relative aspect-video w-full overflow-hidden rounded-md bg-muted">
        {hasCamera ? (
          <img
            data-testid={`printer-snapshot-${printer.id}`}
            src={`/api/v1/printers/${printer.id}/cameras/snapshot.jpg?t=${tick}`}
            alt={`${printer.name} live snapshot`}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            No camera configured
          </div>
        )}
      </div>

      {warmup ? (
        <div
          role="status"
          data-testid={`printer-warmup-${printer.id}`}
          className="flex items-center justify-between rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100"
        >
          <span>Starting monitor… retry in {warmup.retryAfter}s</span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setWarmup(null);
              void fetchState();
            }}
            data-testid={`printer-warmup-retry-${printer.id}`}
          >
            Retry
          </Button>
        </div>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="text-xs text-destructive"
          data-testid={`printer-error-${printer.id}`}
        >
          {error}
        </p>
      ) : null}

      {state && state.state === "printing" ? (
        <div className="space-y-2 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span
              className="truncate text-muted-foreground"
              title={state.current_file ?? undefined}
              data-testid={`printer-file-${printer.id}`}
            >
              {state.current_file ?? "Printing"}
            </span>
            <span
              className="tabular-nums"
              data-testid={`printer-progress-${printer.id}`}
            >
              {state.progress_pct != null
                ? `${Math.round(state.progress_pct)}%`
                : "—"}
            </span>
          </div>
          <div
            className="h-1.5 w-full overflow-hidden rounded bg-muted"
            aria-hidden="true"
          >
            <div
              className="h-full bg-emerald-500"
              style={{
                width: `${Math.min(100, Math.max(0, state.progress_pct ?? 0))}%`,
              }}
            />
          </div>

          {/* Live print telemetry + gcode thumbnail */}
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2">
              <dl className="grid grid-cols-2 gap-x-2 gap-y-1 text-muted-foreground">
                <dt>Speed</dt>
                <dd
                  className="text-foreground tabular-nums"
                  data-testid={`printer-speed-${printer.id}`}
                >
                  {fmtFixed(state.speed_mm_s, 1, "mm/s")}
                </dd>

                <dt>Flow</dt>
                <dd
                  className="text-foreground tabular-nums"
                  data-testid={`printer-flow-${printer.id}`}
                >
                  {fmtFixed(state.flow_mm3_s, 1, "mm³/s")}
                </dd>

                <dt>Filament</dt>
                <dd
                  className="text-foreground tabular-nums"
                  data-testid={`printer-filament-${printer.id}`}
                >
                  {fmtMeters(state.filament_used_mm)}
                </dd>

                <dt>Layer</dt>
                <dd
                  className="text-foreground tabular-nums"
                  data-testid={`printer-layer-${printer.id}`}
                >
                  {state.current_layer != null
                    ? `${state.current_layer}${state.total_layers ? ` / ${state.total_layers}` : ""}`
                    : "—"}
                </dd>

                <dt>Elapsed</dt>
                <dd className="text-foreground tabular-nums">
                  {fmtDuration(state.elapsed_seconds)}
                </dd>

                <dt>ETA</dt>
                <dd className="text-foreground tabular-nums">
                  {fmtDuration(state.remaining_seconds_estimate)}
                </dd>

                <dt>Finish</dt>
                <dd
                  className="text-foreground tabular-nums"
                  data-testid={`printer-finish-${printer.id}`}
                >
                  {fmtEtaClock(state.remaining_seconds_estimate)}
                </dd>
              </dl>
            </div>
            <div className="flex items-center justify-center rounded border border-border bg-muted/40 p-1">
              {thumbnailUrl ? (
                <img
                  alt="Gcode thumbnail"
                  src={thumbnailUrl}
                  className="max-h-24 w-full object-contain"
                  data-testid={`printer-thumbnail-${printer.id}`}
                />
              ) : (
                <span className="text-[10px] text-muted-foreground">
                  No thumbnail
                </span>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {state ? (
        <dl className="grid grid-cols-3 gap-1 text-xs text-muted-foreground">
          <div>
            <dt className="sr-only">Extruder temp</dt>
            <dd>
              E: {state.temperatures?.extruder != null
                ? `${state.temperatures.extruder.toFixed(0)}°`
                : "—"}
            </dd>
          </div>
          <div>
            <dt className="sr-only">Bed temp</dt>
            <dd>
              B: {state.temperatures?.bed != null
                ? `${state.temperatures.bed.toFixed(0)}°`
                : "—"}
            </dd>
          </div>
          <div className="text-right" data-testid={`printer-last-seen-${printer.id}`}>
            {fmtRelative(state.last_seen_at)}
          </div>
        </dl>
      ) : null}
    </article>
  );
}
