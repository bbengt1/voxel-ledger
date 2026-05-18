/**
 * Dynamic line table shared by bill + recurring-bill composers. Each row
 * is `manual` or `expense_category`; the latter surfaces an
 * ExpenseCategoryPicker. Each row also offers an optional expense_account
 * override picker.
 */
import { AccountPicker } from "@/components/ar/AccountPicker";
import { ExpenseCategoryPicker } from "@/components/ap/ExpenseCategoryPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export type BillLineKind = "manual" | "expense_category";

export interface BillLineDraft {
  key: string;
  kind: BillLineKind;
  expenseCategoryId: string;
  description: string;
  quantity: string;
  unitPrice: string;
  vendorSku: string;
  expenseAccountIdOverride: string;
}

let _key = 0;
const nextKey = () => `apln${++_key}`;

export function emptyBillLine(): BillLineDraft {
  return {
    key: nextKey(),
    kind: "manual",
    expenseCategoryId: "",
    description: "",
    quantity: "1",
    unitPrice: "",
    vendorSku: "",
    expenseAccountIdOverride: "",
  };
}

export function billLineNum(v: string): number {
  const n = Number.parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

interface Props {
  lines: BillLineDraft[];
  setLines: (
    next: BillLineDraft[] | ((p: BillLineDraft[]) => BillLineDraft[]),
  ) => void;
  lineExtended: number[];
  hideExtended?: boolean;
}

export function BillLineTable({
  lines,
  setLines,
  lineExtended,
  hideExtended = false,
}: Props) {
  function updateLine(idx: number, patch: Partial<BillLineDraft>) {
    setLines((prev) =>
      prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)),
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Lines</h2>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setLines((p) => [...p, emptyBillLine()])}
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
                  kind: e.target.value as BillLineKind,
                  expenseCategoryId: "",
                })
              }
              data-testid={`line-${idx}-kind`}
            >
              <option value="manual">Manual</option>
              <option value="expense_category">Expense category</option>
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

          {line.kind === "expense_category" ? (
            <ExpenseCategoryPicker
              value={line.expenseCategoryId}
              onChange={(id) => updateLine(idx, { expenseCategoryId: id })}
              data-testid={`line-${idx}-category-picker`}
            />
          ) : null}

          <Input
            value={line.description}
            placeholder="Description"
            onChange={(e) => updateLine(idx, { description: e.target.value })}
            data-testid={`line-${idx}-description`}
          />
          <div className="grid grid-cols-3 gap-2">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={line.quantity}
              onChange={(e) => updateLine(idx, { quantity: e.target.value })}
              placeholder="Qty"
              data-testid={`line-${idx}-quantity`}
            />
            <Input
              type="number"
              min={0}
              step="0.01"
              value={line.unitPrice}
              onChange={(e) => updateLine(idx, { unitPrice: e.target.value })}
              placeholder="Unit price"
              data-testid={`line-${idx}-unit-price`}
            />
            {hideExtended ? (
              <Input
                value={line.vendorSku}
                placeholder="Vendor SKU"
                onChange={(e) => updateLine(idx, { vendorSku: e.target.value })}
                data-testid={`line-${idx}-vendor-sku`}
              />
            ) : (
              <div
                className="flex items-center justify-end pr-2 font-mono text-sm text-muted-foreground"
                data-testid={`line-${idx}-extended`}
              >
                ${(lineExtended[idx] ?? 0).toFixed(2)}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2">
            {!hideExtended ? (
              <Input
                value={line.vendorSku}
                placeholder="Vendor SKU (optional)"
                onChange={(e) => updateLine(idx, { vendorSku: e.target.value })}
                data-testid={`line-${idx}-vendor-sku`}
              />
            ) : null}
            <label className="block text-xs">
              Expense account override
              <AccountPicker
                value={line.expenseAccountIdOverride}
                onChange={(id) =>
                  updateLine(idx, { expenseAccountIdOverride: id })
                }
                filterType="expense"
                placeholder="— Use category default —"
                data-testid={`line-${idx}-account-override`}
              />
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}
