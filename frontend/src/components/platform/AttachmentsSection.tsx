import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type AttachmentResponse = components["schemas"]["AttachmentResponse"];

type EntityKind = "material" | "supply" | "rate" | "product";

export interface AttachmentsSectionProps {
  entityKind: EntityKind;
  entityId: string;
}

// Mirrors the backend cap. Pre-checked client-side so we don't pay the
// upload cost only to bounce off a 413.
const MAX_BYTES = 10 * 1024 * 1024;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Generic attachments pane. Lists uploads, hidden file input for the
 * uploader, per-row download + archive (uploader OR owner).
 */
export function AttachmentsSection({
  entityKind,
  entityId,
}: AttachmentsSectionProps) {
  const role = useAuthStore((s) => s.user?.role);
  const userId = useAuthStore((s) => s.user?.id);
  const isOwner = role === "owner";
  const canUpload = role && role !== "viewer";

  const [items, setItems] = useState<AttachmentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ items: AttachmentResponse[] }>(
        `/api/v1/attachments?entity_kind=${entityKind}&entity_id=${entityId}`,
      );
      setItems(res.data.items);
      setError(null);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to load attachments.";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }, [entityKind, entityId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onFile(file: File) {
    if (file.size > MAX_BYTES) {
      setError(`File is too large (limit ${formatBytes(MAX_BYTES)}).`);
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("entity_kind", entityKind);
      fd.append("entity_id", entityId);
      fd.append("file", file);
      await apiClient.post("/api/v1/attachments", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await load();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Upload failed.";
      setError(detail);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function archive(id: string) {
    try {
      await apiClient.post(`/api/v1/attachments/${id}/archive`);
      await load();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Archive failed.";
      setError(detail);
    }
  }

  return (
    <section
      className="space-y-3 border-t border-border pt-4"
      data-testid="attachments-section"
    >
      <h2 className="text-sm font-semibold">Attachments</h2>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {loading ? <p className="text-sm">Loading attachments…</p> : null}

      {items.length === 0 && !loading ? (
        <p className="text-sm text-muted-foreground">No attachments yet.</p>
      ) : null}

      <ul className="space-y-2">
        {items.map((a) => {
          const isUploader = userId && a.uploaded_by_user_id === userId;
          const canArchive = isOwner || isUploader;
          return (
            <li
              key={a.id}
              data-testid={`attachment-${a.id}`}
              className="flex items-center justify-between gap-2 rounded border border-border p-2 text-sm"
            >
              <div className="flex flex-col">
                <a
                  href={`/api/v1/attachments/${a.id}/download`}
                  className="font-medium text-primary hover:underline"
                  data-testid={`download-${a.id}`}
                >
                  {a.filename}
                </a>
                <span className="text-xs text-muted-foreground">
                  {a.mime_type} · {formatBytes(a.byte_size)}
                </span>
              </div>
              {canArchive ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => archive(a.id)}
                  data-testid={`archive-${a.id}`}
                >
                  Archive
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>

      {canUpload ? (
        <div className="space-y-2" data-testid="attachment-uploader">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            data-testid="attachment-file-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void onFile(file);
            }}
          />
          <Button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            data-testid="attachment-upload-btn"
          >
            {uploading ? "Uploading…" : "Upload file"}
          </Button>
          <p className="text-xs text-muted-foreground">
            Max {formatBytes(MAX_BYTES)} per file.
          </p>
        </div>
      ) : null}
    </section>
  );
}
