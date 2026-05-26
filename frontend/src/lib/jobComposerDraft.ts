/**
 * Persist + restore an in-progress JobComposer form across a brief
 * detour (e.g. routing to /catalog/materials/new to create a material
 * that was discovered on a gcode but isn't in the catalog yet).
 *
 * Stored in ``sessionStorage`` under a deterministic key. The shape is
 * intentionally loose (everything serialized as JSON strings/null) so
 * adding a new field to the composer doesn't require touching this
 * helper.
 */

const STORAGE_KEY = "voxel-ledger.job-composer-draft.v1";

export interface PendingMaterialSlot {
  /** Plate index in the composer ``plates`` array. */
  plateIdx: number;
  /** Stable key of the material draft row whose ``material`` is null. */
  slotKey: string;
}

export interface JobComposerDraft {
  // Free-text composer state, mirroring useState declarations.
  customer: string;
  quantityOrdered: string;
  priority: string;
  dueAt: string;
  notes: string;
  product: { id: string; label: string } | null;
  plates: unknown[]; // PlateDraft[] — opaque to this helper
  /** Where to splice in the just-created material id when we return. */
  pending: PendingMaterialSlot | null;
}

export function saveJobComposerDraft(draft: JobComposerDraft): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  } catch {
    /* sessionStorage may be unavailable — silently degrade */
  }
}

export function loadJobComposerDraft(): JobComposerDraft | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as JobComposerDraft;
  } catch {
    return null;
  }
}

export function clearJobComposerDraft(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
