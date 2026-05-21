/**
 * Reusable preview-then-confirm dialog for the Phase 11.3 batch
 * operations API (#195). Used by the customer + product list pages
 * for the ``archive`` action.
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "@/components/ui/Dialog";

type Preview = components["schemas"]["BatchPreviewResponse"];
type Commit = components["schemas"]["BatchCommitResponse"];

export interface BatchOpsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entity: string;
  action: string;
  ids: string[];
  params?: Record<string, unknown>;
  /** Friendly label, e.g. "Archive 3 customers". */
  title: string;
  onCommitted?: (result: Commit) => void;
}

export function BatchOpsDialog({
  open,
  onOpenChange,
  entity,
  action,
  ids,
  params,
  title,
  onCommitted,
}: BatchOpsDialogProps) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Commit | null>(null);

  useEffect(() => {
    if (!open) {
      setPreview(null);
      setResult(null);
      setError(null);
      return;
    }
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const resp = await api.post(
          "/api/v1/batch/preview",
          { entity, action, ids, params: params ?? {} },
        );
        if (!cancelled) setPreview(resp.data as Preview);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Preview failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [open, entity, action, ids, params]);

  async function onConfirm() {
    setCommitting(true);
    setError(null);
    try {
      const resp = await api.post(
        "/api/v1/batch/commit",
        { entity, action, ids, params: params ?? {} },
      );
      const body = resp.data as Commit;
      setResult(body);
      onCommitted?.(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Commit failed");
    } finally {
      setCommitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPortal>
        <DialogOverlay />
        <DialogContent
          data-testid="batch-ops-dialog"
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded bg-background p-4 shadow-lg"
        >
          <DialogTitle className="text-lg font-medium">{title}</DialogTitle>
          {error ? <div className="pt-2 text-sm text-red-600">{error}</div> : null}
          {loading ? (
            <div className="pt-3 text-sm text-muted-foreground">Loading preview...</div>
          ) : null}
          {preview && !result ? (
            <div className="pt-3 space-y-3">
              <div>
                <span className="font-medium">{preview.matched_count}</span> rows
                matched
                {preview.blockers.length > 0
                  ? `; ${preview.blockers.length} will be skipped`
                  : ""}
                .
              </div>
              {preview.blockers.length > 0 ? (
                <div data-testid="batch-ops-blockers">
                  <div className="text-sm font-medium">Blockers:</div>
                  <ul className="pt-1 text-xs space-y-0.5">
                    {preview.blockers.slice(0, 5).map((b) => (
                      <li key={b.id} className="font-mono">
                        {b.id} — {b.reason}
                      </li>
                    ))}
                    {preview.blockers.length > 5 ? (
                      <li className="text-muted-foreground">
                        +{preview.blockers.length - 5} more
                      </li>
                    ) : null}
                  </ul>
                </div>
              ) : null}
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  data-testid="batch-ops-confirm"
                  onClick={() => void onConfirm()}
                  disabled={committing || preview.matched_count === 0}
                >
                  {committing ? "Applying..." : "Confirm"}
                </Button>
              </div>
            </div>
          ) : null}
          {result ? (
            <div className="pt-3 space-y-2 text-sm">
              <div data-testid="batch-ops-result">
                Applied <span className="font-medium">{result.applied}</span>,
                skipped <span className="font-medium">{result.skipped}</span>.
              </div>
              <div className="text-xs text-muted-foreground">
                Audit id: <code>{result.audit_id}</code>
              </div>
              <div className="flex justify-end pt-2">
                <Button type="button" onClick={() => onOpenChange(false)}>
                  Close
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </DialogPortal>
    </Dialog>
  );
}
