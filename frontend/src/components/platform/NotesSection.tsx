import { useCallback, useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { renderMarkdown } from "@/lib/markdown";
import { useAuthStore } from "@/store/useAuthStore";

type NoteResponse = components["schemas"]["NoteResponse"];

type EntityKind = "material" | "supply" | "rate" | "product";

export interface NotesSectionProps {
  entityKind: EntityKind;
  entityId: string;
}

/**
 * Generic notes pane for any catalog detail page. Lists pinned notes
 * first, then chronological. Composer at the bottom. Edit-in-place for
 * the author (or owner). Pin/unpin visible to owner only.
 */
export function NotesSection({ entityKind, entityId }: NotesSectionProps) {
  const role = useAuthStore((s) => s.user?.role);
  const userId = useAuthStore((s) => s.user?.id);
  const isOwner = role === "owner";
  const canWrite = role && role !== "viewer";

  const [notes, setNotes] = useState<NoteResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [composerBody, setComposerBody] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingBody, setEditingBody] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ items: NoteResponse[] }>(
        `/api/v1/notes?entity_kind=${entityKind}&entity_id=${entityId}`,
      );
      setNotes(res.data.items);
      setError(null);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to load notes.";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }, [entityKind, entityId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submitNew() {
    if (!composerBody.trim()) return;
    setSubmitting(true);
    try {
      await apiClient.post("/api/v1/notes", {
        entity_kind: entityKind,
        entity_id: entityId,
        body: composerBody,
      });
      setComposerBody("");
      await load();
    } finally {
      setSubmitting(false);
    }
  }

  async function saveEdit(id: string) {
    if (!editingBody.trim()) return;
    try {
      await apiClient.patch(`/api/v1/notes/${id}`, { body: editingBody });
      setEditingId(null);
      setEditingBody("");
      await load();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to save.";
      setError(detail);
    }
  }

  async function deleteNote(id: string) {
    try {
      await apiClient.delete(`/api/v1/notes/${id}`);
      await load();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to delete.";
      setError(detail);
    }
  }

  async function togglePin(note: NoteResponse) {
    try {
      const path = note.is_pinned
        ? `/api/v1/notes/${note.id}/unpin`
        : `/api/v1/notes/${note.id}/pin`;
      await apiClient.post(path);
      await load();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to pin.";
      setError(detail);
    }
  }

  const ordered = useMemo(() => {
    // The API already returns pinned-first, but sort defensively in case
    // a refetch races.
    return [...notes].sort((a, b) => {
      if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
      return b.created_at.localeCompare(a.created_at);
    });
  }, [notes]);

  return (
    <section
      className="space-y-3 border-t border-border pt-4"
      data-testid="notes-section"
    >
      <h2 className="text-sm font-semibold">Notes</h2>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {loading ? <p className="text-sm">Loading notes…</p> : null}

      <ul className="space-y-3">
        {ordered.map((note) => {
          const isAuthor = userId && note.author_user_id === userId;
          const canEditDelete = isOwner || isAuthor;
          const isEditing = editingId === note.id;
          return (
            <li
              key={note.id}
              data-testid={`note-${note.id}`}
              className="rounded border border-border p-3 text-sm"
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  {new Date(note.created_at).toLocaleString()}
                  {note.is_pinned ? " · pinned" : ""}
                </span>
                <div className="flex gap-2">
                  {isOwner ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => togglePin(note)}
                      data-testid={`pin-${note.id}`}
                    >
                      {note.is_pinned ? "Unpin" : "Pin"}
                    </Button>
                  ) : null}
                  {canEditDelete && !isEditing ? (
                    <>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditingId(note.id);
                          setEditingBody(note.body);
                        }}
                        data-testid={`edit-${note.id}`}
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => deleteNote(note.id)}
                        data-testid={`delete-${note.id}`}
                      >
                        Delete
                      </Button>
                    </>
                  ) : null}
                </div>
              </div>
              {isEditing ? (
                <div className="space-y-2">
                  <textarea
                    className="w-full rounded border border-input bg-background p-2 text-sm"
                    rows={4}
                    value={editingBody}
                    onChange={(e) => setEditingBody(e.target.value)}
                    data-testid={`edit-body-${note.id}`}
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => saveEdit(note.id)}
                      data-testid={`save-${note.id}`}
                    >
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingId(null);
                        setEditingBody("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div
                  className="prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{
                    __html: renderMarkdown(note.body),
                  }}
                />
              )}
            </li>
          );
        })}
      </ul>

      {canWrite ? (
        <div className="space-y-2" data-testid="note-composer">
          <textarea
            className="w-full rounded border border-input bg-background p-2 text-sm"
            rows={3}
            placeholder="Add a note (markdown supported)…"
            value={composerBody}
            onChange={(e) => setComposerBody(e.target.value)}
            data-testid="note-composer-body"
          />
          <Button
            onClick={submitNew}
            disabled={submitting || !composerBody.trim()}
            data-testid="note-submit"
          >
            {submitting ? "Posting…" : "Post note"}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
