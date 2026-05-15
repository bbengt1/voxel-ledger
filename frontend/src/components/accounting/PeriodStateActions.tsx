/**
 * Per-row period action buttons: state-machine aware + role aware.
 *
 * - open: Close (owner+bookkeeper)
 * - closed: Reopen (owner+bookkeeper); Lock (owner-only, confirmation)
 * - locked: no actions
 */
import { useState } from "react";

import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";

type AccountingPeriodResponse =
  components["schemas"]["AccountingPeriodResponse"];

const ADMIN = new Set(["owner", "bookkeeper"]);
const OWNER = new Set(["owner"]);

interface Props {
  period: AccountingPeriodResponse;
  role: string | undefined;
  busy: boolean;
  onAction: (
    period: AccountingPeriodResponse,
    action: "close" | "reopen" | "lock",
  ) => void;
}

export function PeriodStateActions({ period, role, busy, onAction }: Props) {
  const isAdmin = !!role && ADMIN.has(role);
  const isOwner = !!role && OWNER.has(role);
  const [lockOpen, setLockOpen] = useState(false);

  if (period.state === "open" && isAdmin) {
    return (
      <Button
        size="sm"
        variant="outline"
        onClick={() => onAction(period, "close")}
        disabled={busy}
        data-testid={`close-${period.id}`}
      >
        Close
      </Button>
    );
  }

  if (period.state === "closed") {
    return (
      <div className="flex gap-2">
        {isAdmin ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onAction(period, "reopen")}
            disabled={busy}
            data-testid={`reopen-${period.id}`}
          >
            Reopen
          </Button>
        ) : null}
        {isOwner ? (
          <>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setLockOpen(true)}
              disabled={busy}
              data-testid={`lock-${period.id}`}
            >
              Lock
            </Button>
            <Dialog open={lockOpen} onOpenChange={setLockOpen}>
              <DialogContent data-testid="lock-dialog">
                <DialogTitle>Lock this period?</DialogTitle>
                <p className="mt-2 text-sm text-muted-foreground">
                  This is permanent — locked periods cannot be reopened.
                </p>
                <div className="mt-4 flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setLockOpen(false)}
                    disabled={busy}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => {
                      setLockOpen(false);
                      onAction(period, "lock");
                    }}
                    disabled={busy}
                    data-testid="confirm-lock"
                  >
                    Lock permanently
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </>
        ) : null}
      </div>
    );
  }

  return <span className="text-xs text-muted-foreground">—</span>;
}
