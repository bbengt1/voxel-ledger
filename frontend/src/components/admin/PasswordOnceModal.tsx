import { useState } from "react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";

export interface PasswordOnceModalProps {
  open: boolean;
  /** Called when the modal is dismissed (acknowledged or otherwise). */
  onClose: () => void;
  /** The generated password to display. Empty string treated as "no password yet". */
  password: string;
  /** Heading copy, e.g. "User created" or "Password reset". */
  title: string;
  /** Secondary copy explaining what to do with the password. */
  description?: string;
}

/**
 * Shows a freshly-generated password exactly once. The caller controls
 * the open state; closing without acknowledging is allowed but produces
 * a warning so the user has a chance to back out and copy.
 */
export function PasswordOnceModal({
  open,
  onClose,
  password,
  title,
  description,
}: PasswordOnceModalProps) {
  const [copied, setCopied] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [showWarning, setShowWarning] = useState(false);

  function reset() {
    setCopied(false);
    setAcknowledged(false);
    setShowWarning(false);
  }

  async function copyToClipboard() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
    } catch {
      // Clipboard might be unavailable (insecure context, e.g. http).
      // Fall back to showing the user the value — it's already on screen.
      setCopied(false);
    }
  }

  function handleClose() {
    if (!acknowledged) {
      setShowWarning(true);
      return;
    }
    reset();
    onClose();
  }

  function handleForceClose() {
    reset();
    onClose();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) handleClose();
      }}
    >
      <DialogContent aria-describedby="pwd-modal-desc">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription id="pwd-modal-desc">
          {description ??
            "This password is shown only once. Copy it now — there is no way to retrieve it later."}
        </DialogDescription>

        <div className="mt-4 space-y-3">
          <div
            className="rounded border border-border bg-muted p-3 font-mono text-sm select-all"
            data-testid="generated-password"
            aria-label="generated password"
          >
            {password}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" onClick={copyToClipboard}>
              {copied ? "Copied" : "Copy to clipboard"}
            </Button>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => {
                  setAcknowledged(e.target.checked);
                  if (e.target.checked) setShowWarning(false);
                }}
                data-testid="ack-saved"
              />
              I&rsquo;ve saved this password
            </label>
          </div>

          {showWarning ? (
            <div
              role="alert"
              data-testid="save-warning"
              className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
            >
              Did you save it? You won&rsquo;t see this password again.
              <div className="mt-2 flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowWarning(false)}
                >
                  Go back
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={handleForceClose}
                  data-testid="close-anyway"
                >
                  Close anyway
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex justify-end">
              <DialogClose asChild>
                <Button type="button">Done</Button>
              </DialogClose>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
