/**
 * Divisions CRUD list.
 *
 * Owner-only writes (archive + create + rename), everyone with the page
 * reads. Mirrors the inventory locations list pattern.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type DivisionResponse = components["schemas"]["DivisionResponse"];

const OWNER = new Set(["owner"]);

export function DivisionsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = !!role && OWNER.has(role);

  const [items, setItems] = useState<DivisionResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [newOpen, setNewOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    const params: Record<string, string> = {};
    if (!includeArchived) params["is_archived"] = "false";
    api
      .get("/api/v1/accounting/divisions", { params })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load divisions.";
        setError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [includeArchived, reloadKey]);

  async function saveRename(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiClient.patch(`/api/v1/accounting/divisions/${id}`, {
        name: editName.trim(),
      });
      setEditingId(null);
      setReloadKey((k) => k + 1);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Rename failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function archive(id: string) {
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/accounting/divisions/${id}/archive`, {});
      setReloadKey((k) => k + 1);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Archive failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function unarchive(id: string) {
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/accounting/divisions/${id}/unarchive`, {});
      setReloadKey((k) => k + 1);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Unarchive failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  const columns: DataTableColumn<DivisionResponse>[] = [
    {
      key: "code",
      header: "Code",
      isPrimary: true,
      cell: (d) => <span className="font-mono text-xs">{d.code}</span>,
    },
    {
      key: "name",
      header: "Name",
      cell: (d) =>
        editingId === d.id ? (
          <Input
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            data-testid={`edit-name-${d.id}`}
          />
        ) : (
          d.name
        ),
    },
    {
      key: "status",
      header: "Status",
      cell: (d) => (
        <span className="text-xs">{d.is_archived ? "Archived" : "Active"}</span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      align: "right",
      cardFullWidth: true,
      cell: (d) =>
        canWrite ? (
          editingId === d.id ? (
            <div className="flex justify-end gap-2">
              <Button
                size="sm"
                onClick={() => saveRename(d.id)}
                disabled={busy || !editName.trim()}
                data-testid={`save-${d.id}`}
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setEditingId(null)}
                disabled={busy}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <div className="flex justify-end gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setEditingId(d.id);
                  setEditName(d.name);
                }}
                disabled={busy || d.is_archived}
                data-testid={`rename-${d.id}`}
              >
                Rename
              </Button>
              {d.is_archived ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => unarchive(d.id)}
                  disabled={busy}
                  data-testid={`unarchive-${d.id}`}
                >
                  Unarchive
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => archive(d.id)}
                  disabled={busy}
                  data-testid={`archive-${d.id}`}
                >
                  Archive
                </Button>
              )}
            </div>
          )
        ) : null,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Divisions"
        actions={
          canWrite ? (
            <Button onClick={() => setNewOpen(true)} data-testid="open-new-division">
              New division
            </Button>
          ) : null
        }
      />

      <label className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          checked={includeArchived}
          onChange={(e) => setIncludeArchived(e.target.checked)}
          data-testid="filter-archived"
        />
        Show archived
      </label>

      {error ? (
        <div role="alert" data-testid="divisions-error" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(d) => d.id}
        emptyMessage="No divisions."
        minWidthClassName="min-w-[560px]"
      />

      <NewDivisionDialog
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={() => {
          setNewOpen(false);
          setReloadKey((k) => k + 1);
        }}
      />
    </section>
  );
}

function NewDivisionDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setCode("");
      setName("");
      setError(null);
    }
  }, [open]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post("/api/v1/accounting/divisions", {
        code: code.trim(),
        name: name.trim(),
      });
      onCreated();
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Create failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? onClose() : undefined)}>
      <DialogContent data-testid="new-division-dialog">
        <DialogTitle>New division</DialogTitle>
        <div className="mt-3 flex flex-col gap-2">
          {error ? (
            <div
              role="alert"
              data-testid="new-division-error"
              className="rounded border border-destructive bg-destructive/10 p-2 text-xs text-destructive"
            >
              {error}
            </div>
          ) : null}
          <label className="flex flex-col gap-1 text-xs">
            Code
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              data-testid="new-division-code"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            Name
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="new-division-name"
            />
          </label>
          <div className="mt-2 flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={submit}
              disabled={busy || !code.trim() || !name.trim()}
              data-testid="submit-new-division"
            >
              Create
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
