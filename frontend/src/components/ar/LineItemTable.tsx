/**
 * Shared dynamic line table for quote + invoice composers. Each row is
 * `manual` / `product` / `job`; product picker auto-fills description +
 * unit price. Matches the SaleComposer line UX.
 */
import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import {
  EntityPicker,
  type EntityOption,
} from "@/components/inventory/EntityPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type JobResponse = components["schemas"]["JobResponse"];

export type LineKind = "product" | "job" | "manual";

export interface LineDraft {
  key: string;
  kind: LineKind;
  product: EntityOption | null;
  jobId: string;
  description: string;
  quantity: string;
  unitPrice: string;
  skuOrJobNumber: string;
  /** Optional billable-source tag stamped when a line was pulled from a
   *  bill item or expense-claim line (Phase 8.12a). */
  billableSource?: {
    kind: "bill_item" | "expense_claim_line";
    id: string;
  } | null;
}

let _key = 0;
const nextKey = () => `arln${++_key}`;

export function emptyLine(): LineDraft {
  return {
    key: nextKey(),
    kind: "manual",
    product: null,
    jobId: "",
    description: "",
    quantity: "1",
    unitPrice: "",
    skuOrJobNumber: "",
  };
}

export function lineNum(v: string): number {
  const n = Number.parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

interface Props {
  lines: LineDraft[];
  setLines: (next: LineDraft[] | ((p: LineDraft[]) => LineDraft[])) => void;
  lineExtended: number[];
}

export function LineItemTable({ lines, setLines, lineExtended }: Props) {
  const [completedJobs, setCompletedJobs] = useState<JobResponse[]>([]);

  useEffect(() => {
    api
      .get("/api/v1/jobs", { params: { state: "completed" } })
      .then((res) => setCompletedJobs(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  function updateLine(idx: number, patch: Partial<LineDraft>) {
    setLines((prev) =>
      prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)),
    );
  }

  const onPickProduct = useCallback(
    async (idx: number, opt: EntityOption | null) => {
      updateLine(idx, { product: opt });
      if (!opt) return;
      try {
        const res = await api.get(
          `/api/v1/products/${opt.id}` as "/api/v1/products/{product_id}",
        );
        const p = res.data as unknown as {
          name: string;
          sku?: string | null;
          unit_price: string;
        };
        updateLine(idx, {
          description: p.name,
          unitPrice: p.unit_price,
          skuOrJobNumber: p.sku ?? "",
        });
      } catch {
        /* non-fatal — operator can edit */
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  function onPickJob(idx: number, jobId: string) {
    const job = completedJobs.find((j) => j.id === jobId);
    if (!job) {
      updateLine(idx, { jobId });
      return;
    }
    updateLine(idx, {
      jobId,
      description: `Job ${job.job_number}`,
      skuOrJobNumber: job.job_number,
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Lines</h2>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setLines((p) => [...p, emptyLine()])}
          data-testid="add-line-btn"
        >
          Add line
        </Button>
      </div>

      {lines.map((line, idx) => (
        <div
          key={line.key}
          className="space-y-2 rounded-lg border border-border p-3"
          data-testid={`line-row-${idx}`}
        >
          <div className="flex items-center justify-between">
            <select
              className="h-8 rounded-md border border-input bg-background px-2 text-xs"
              value={line.kind}
              onChange={(e) =>
                updateLine(idx, {
                  kind: e.target.value as LineKind,
                  product: null,
                  jobId: "",
                })
              }
              data-testid={`line-${idx}-kind`}
            >
              <option value="manual">Manual</option>
              <option value="product">Product</option>
              <option value="job">Job</option>
            </select>
            {lines.length > 1 ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setLines((p) => p.filter((_, i) => i !== idx))}
                data-testid={`remove-line-${idx}`}
              >
                ×
              </Button>
            ) : null}
          </div>

          {line.kind === "product" ? (
            <EntityPicker
              kind="product"
              value={line.product}
              onChange={(opt) => void onPickProduct(idx, opt)}
              data-testid={`line-${idx}-product-picker`}
            />
          ) : line.kind === "job" ? (
            <select
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={line.jobId}
              onChange={(e) => onPickJob(idx, e.target.value)}
              data-testid={`line-${idx}-job-picker`}
            >
              <option value="">— Pick completed job —</option>
              {completedJobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.job_number} ({j.pieces_produced} pcs)
                </option>
              ))}
            </select>
          ) : null}

          <Input
            value={line.description}
            placeholder="Description"
            onChange={(e) => updateLine(idx, { description: e.target.value })}
            data-testid={`line-${idx}-description`}
          />
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <label className="block text-xs text-muted-foreground sm:sr-only">
              Qty
              <Input
                type="number"
                min={0}
                step="0.01"
                value={line.quantity}
                onChange={(e) => updateLine(idx, { quantity: e.target.value })}
                placeholder="Qty"
                data-testid={`line-${idx}-quantity`}
              />
            </label>
            <label className="block text-xs text-muted-foreground sm:sr-only">
              Unit price
              <Input
                type="number"
                min={0}
                step="0.01"
                value={line.unitPrice}
                onChange={(e) => updateLine(idx, { unitPrice: e.target.value })}
                placeholder="Unit price"
                data-testid={`line-${idx}-unit-price`}
              />
            </label>
            <div
              className="flex items-center justify-between pr-2 font-mono text-sm text-muted-foreground sm:justify-end"
              data-testid={`line-${idx}-extended`}
            >
              <span className="text-xs sm:hidden">Extended</span>
              <span>${(lineExtended[idx] ?? 0).toFixed(2)}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
