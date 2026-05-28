/**
 * Modal: browse gcode files on any configured printer and use one to
 * populate a plate. Pick a printer → fetch its file list → preview
 * thumbnails → on selection, POST ``/jobs/discover-from-printer`` and
 * hand the resulting ``DiscoveredPlateResponse`` back to the caller.
 *
 * Thumbnails are loaded via authenticated axios (Bearer header) and
 * rendered through blob URLs — the same pattern used by the monitor
 * card, since ``<img src>`` can't carry the Authorization header.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";

type PrinterResponse = components["schemas"]["PrinterResponse"];
type DiscoveredPlate = components["schemas"]["DiscoveredPlateResponse"];

interface GcodeFileRow {
  path: string;
  size: number | null;
  modified: number | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onPicked: (plate: DiscoveredPlate) => void;
}

const THUMB_TIMEOUT_MS = 8000;

function fmtBytes(n: number | null): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtDate(epoch: number | null): string {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleString();
}

export function PrinterFileBrowser({ open, onClose, onPicked }: Props) {
  const [printers, setPrinters] = useState<PrinterResponse[]>([]);
  const [printerId, setPrinterId] = useState<string>("");
  const [files, setFiles] = useState<GcodeFileRow[]>([]);
  const [loadingPrinters, setLoadingPrinters] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const [picking, setPicking] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  // Load printers on open.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingPrinters(true);
    setError(null);
    apiClient
      .get<{ items: PrinterResponse[] }>("/api/v1/printers", {
        params: { is_archived: "false" },
      })
      .then((res) => {
        if (cancelled) return;
        const eligible = res.data.items.filter((p) => !!p.moonraker_url);
        setPrinters(eligible);
        if (eligible[0] && !printerId) setPrinterId(eligible[0].id);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load printers.");
      })
      .finally(() => {
        if (!cancelled) setLoadingPrinters(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Reset state when the modal closes.
  useEffect(() => {
    if (!open) {
      setFiles([]);
      setThumbs((prev) => {
        Object.values(prev).forEach((url) => {
          if (url) URL.revokeObjectURL(url);
        });
        return {};
      });
      setError(null);
      setFilter("");
      setPicking(null);
    }
  }, [open]);

  // Load file list when a printer is selected.
  const loadFiles = useCallback(async () => {
    if (!printerId) return;
    setLoadingFiles(true);
    setError(null);
    try {
      const res = await apiClient.get<{ items: GcodeFileRow[] }>(
        `/api/v1/printers/${printerId}/gcode-files`,
      );
      setFiles(res.data.items);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not list files.";
      setError(typeof detail === "string" ? detail : "Could not list files.");
      setFiles([]);
    } finally {
      setLoadingFiles(false);
    }
  }, [printerId]);

  useEffect(() => {
    if (open && printerId) void loadFiles();
  }, [open, printerId, loadFiles]);

  // Lazy-load thumbnails for the visible (filtered) list. Re-runs when
  // the file list or filter changes; revokes blob URLs on cleanup.
  const visibleFiles = useMemo(() => {
    const f = filter.trim().toLowerCase();
    if (!f) return files;
    return files.filter((row) => row.path.toLowerCase().includes(f));
  }, [files, filter]);

  useEffect(() => {
    if (!printerId) return;
    let cancelled = false;
    const newUrls: Record<string, string> = {};
    // Limit thumbnail fetching to the first ~40 visible files to avoid
    // hammering the printer when the catalog is huge.
    const subset = visibleFiles.slice(0, 40);
    const controller = new AbortController();
    Promise.all(
      subset.map(async (row) => {
        if (cancelled) return;
        try {
          const res = await apiClient.get<Blob>(
            `/api/v1/printers/${printerId}/gcode/thumbnail.png`,
            {
              params: { filename: row.path },
              responseType: "blob",
              signal: controller.signal,
              timeout: THUMB_TIMEOUT_MS,
            },
          );
          if (cancelled) return;
          const url = URL.createObjectURL(res.data);
          newUrls[row.path] = url;
          setThumbs((prev) => ({ ...prev, [row.path]: url }));
        } catch {
          if (!cancelled)
            setThumbs((prev) => ({ ...prev, [row.path]: null }));
        }
      }),
    );
    return () => {
      cancelled = true;
      controller.abort();
      // Revoke any thumbnail URLs created on this pass.
      Object.values(newUrls).forEach((u) => URL.revokeObjectURL(u));
    };
  }, [printerId, visibleFiles]);

  async function onPickFile(path: string) {
    if (!printerId) return;
    setPicking(path);
    setError(null);
    try {
      const res = await apiClient.post<DiscoveredPlate>(
        "/api/v1/jobs/discover-from-printer",
        { printer_id: printerId, filename: path },
      );
      onPicked(res.data);
      onClose();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not read file.";
      setError(typeof detail === "string" ? detail : "Could not read file.");
    } finally {
      setPicking(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-hidden">
        <DialogTitle>Browse printer files</DialogTitle>
        <DialogDescription>
          Pick a gcode file from any configured printer to populate this
          plate. Print time, filament, and object count are read from the
          file's slicer metadata.
        </DialogDescription>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            Printer
            <select
              className="rounded border border-input bg-background px-2 py-1 text-sm"
              value={printerId}
              onChange={(e) => setPrinterId(e.target.value)}
              disabled={loadingPrinters || printers.length === 0}
              data-testid="browser-printer-select"
            >
              {printers.length === 0 ? (
                <option value="">No printers with Moonraker URL</option>
              ) : (
                printers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))
              )}
            </select>
          </label>
          <label className="flex flex-1 items-center gap-2 text-sm">
            <span className="sr-only">Filter</span>
            <input
              type="text"
              placeholder="Filter by filename…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full rounded border border-input bg-background px-2 py-1 text-sm"
              data-testid="browser-filter"
            />
          </label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={loadFiles}
            disabled={!printerId || loadingFiles}
            data-testid="browser-refresh"
          >
            Refresh
          </Button>
        </div>

        {error ? (
          <p
            role="alert"
            className="mt-3 text-sm text-destructive"
            data-testid="browser-error"
          >
            {error}
          </p>
        ) : null}

        <div className="mt-3 max-h-[55vh] overflow-y-auto rounded border border-border">
          {loadingFiles ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : visibleFiles.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              {files.length === 0 ? "No gcode files." : "No files match the filter."}
            </p>
          ) : (
            <ul
              className="divide-y divide-border"
              data-testid="browser-file-list"
            >
              {visibleFiles.map((row) => {
                const thumb = thumbs[row.path];
                const isPicking = picking === row.path;
                return (
                  <li
                    key={row.path}
                    className="flex items-center gap-3 p-2 hover:bg-muted/30"
                  >
                    <div className="flex h-14 w-14 flex-none items-center justify-center rounded bg-muted/40">
                      {thumb ? (
                        <img
                          src={thumb}
                          alt=""
                          className="max-h-14 max-w-14 object-contain"
                        />
                      ) : (
                        <span className="text-[10px] text-muted-foreground">
                          —
                        </span>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p
                        className="truncate text-sm font-medium"
                        title={row.path}
                      >
                        {row.path}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {fmtBytes(row.size)} · {fmtDate(row.modified)}
                      </p>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => onPickFile(row.path)}
                      disabled={!!picking}
                      data-testid={`browser-pick-${row.path}`}
                    >
                      {isPicking ? "Reading…" : "Use"}
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="mt-3 flex justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={!!picking}
          >
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
