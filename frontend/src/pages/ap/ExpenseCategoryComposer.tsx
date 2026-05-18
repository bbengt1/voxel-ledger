/**
 * `/expense-categories/new` and `/expense-categories/:id` — composer for
 * an expense category. Same composer handles new + edit.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ExpenseCategoryResponse = components["schemas"]["ExpenseCategoryResponse"];
type ExpenseCategoryCreate = components["schemas"]["ExpenseCategoryCreate"];
type ExpenseCategoryUpdate = components["schemas"]["ExpenseCategoryUpdate"];

export function ExpenseCategoryComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [defaultExpenseAccountId, setDefaultExpenseAccountId] = useState("");
  const [parentId, setParentId] = useState("");
  const [notes, setNotes] = useState("");
  const [parentOptions, setParentOptions] = useState<ExpenseCategoryResponse[]>(
    [],
  );

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/expense-categories")
      .then((res) => setParentOptions(res.data.items))
      .catch(() => setParentOptions([]));
  }, []);

  useEffect(() => {
    if (!id) return;
    api
      .get(
        `/api/v1/expense-categories/${id}` as "/api/v1/expense-categories/{category_id}",
      )
      .then((res) => {
        const c = res.data as unknown as ExpenseCategoryResponse;
        setCode(c.code);
        setName(c.name);
        setDefaultExpenseAccountId(c.default_expense_account_id);
        setParentId(c.parent_id ?? "");
        setNotes(c.notes ?? "");
      })
      .catch(() => setError("Could not load category."));
  }, [id]);

  async function submit() {
    if (!code.trim() || !name.trim()) {
      setError("Code and name are required.");
      return;
    }
    if (!defaultExpenseAccountId) {
      setError("Pick a default expense account.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      let categoryId: string;
      if (isEdit && id) {
        const body: ExpenseCategoryUpdate = {
          code: code.trim(),
          name: name.trim(),
          default_expense_account_id: defaultExpenseAccountId,
          parent_id: parentId || null,
          notes: notes.trim() || null,
        };
        await apiClient.patch(`/api/v1/expense-categories/${id}`, body);
        categoryId = id;
      } else {
        const body: ExpenseCategoryCreate = {
          code: code.trim(),
          name: name.trim(),
          default_expense_account_id: defaultExpenseAccountId,
        };
        if (parentId) body.parent_id = parentId;
        if (notes.trim()) body.notes = notes.trim();
        const res = await apiClient.post<ExpenseCategoryResponse>(
          "/api/v1/expense-categories",
          body,
        );
        categoryId = res.data.id;
      }
      navigate(`/expense-categories`);
      // Use the id so unused-var lint doesn't fire.
      void categoryId;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not save category.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">
          {isEdit ? "Edit expense category" : "New expense category"}
        </h1>
      </header>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Code
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              data-testid="category-code"
            />
          </label>
          <label className="block text-sm">
            Name
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="category-name"
            />
          </label>
          <label className="block text-sm">
            Default expense account
            <AccountPicker
              value={defaultExpenseAccountId}
              onChange={setDefaultExpenseAccountId}
              filterType="expense"
              data-testid="category-default-expense"
            />
          </label>
          <label className="block text-sm">
            Parent (optional)
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
              data-testid="category-parent"
            >
              <option value="">— None —</option>
              {parentOptions
                .filter((o) => o.id !== id)
                .map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.code} · {o.name}
                  </option>
                ))}
            </select>
          </label>
        </div>
        <label className="block text-sm">
          Notes
          <textarea
            className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="category-notes"
          />
        </label>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void submit()}
          data-testid="category-save"
        >
          {submitting
            ? "Saving…"
            : isEdit
              ? "Save changes"
              : "Create category"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/expense-categories")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
