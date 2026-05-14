import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PasswordOnceModal } from "@/components/admin/PasswordOnceModal";
import { Form, FormField } from "@/components/form/Form";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type Role = components["schemas"]["Role"];

// Mirrors UserCreateRequest from the generated types.
const createSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  full_name: z.string().min(1, "Full name is required."),
  role: z.enum(["owner", "bookkeeper", "production", "sales", "viewer"]),
});

type CreateValues = z.infer<typeof createSchema>;

const ROLES: Role[] = ["owner", "bookkeeper", "production", "sales", "viewer"];

function CreateFields({ submitting }: { submitting: boolean }) {
  const { register } = useFormContext<CreateValues>();
  return (
    <>
      <FormField name="email" label="Email">
        <Input
          id="email"
          type="email"
          autoComplete="off"
          disabled={submitting}
          {...register("email")}
        />
      </FormField>
      <FormField name="full_name" label="Full name">
        <Input
          id="full_name"
          autoComplete="off"
          disabled={submitting}
          {...register("full_name")}
        />
      </FormField>
      <FormField name="role" label="Role">
        <select
          id="role"
          className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          disabled={submitting}
          {...register("role")}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </FormField>
    </>
  );
}

export function UserCreatePage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [password, setPassword] = useState<string | null>(null);
  const [createdUserId, setCreatedUserId] = useState<string | null>(null);

  const onSubmit = async (values: CreateValues) => {
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await api.post("/api/v1/users", values);
      setPassword(res.data.generated_password);
      setCreatedUserId(res.data.user.id);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not create user.";
      setFormError(typeof detail === "string" ? detail : "Could not create user.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleModalClose = () => {
    setPassword(null);
    if (createdUserId) navigate(`/admin/users/${createdUserId}`);
    else navigate("/admin/users");
  };

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New user</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        A password is generated automatically and shown once after creation.
      </p>

      <Form
        schema={createSchema}
        defaultValues={{ email: "", full_name: "", role: "sales" }}
        onSubmit={onSubmit}
        className="mt-6"
      >
        <CreateFields submitting={submitting} />
        {formError ? (
          <p role="alert" data-testid="create-error" className="text-sm text-destructive">
            {formError}
          </p>
        ) : null}
        <div className="flex gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create user"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/admin/users")}
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </Form>

      <PasswordOnceModal
        open={password !== null}
        password={password ?? ""}
        title="User created"
        description="This is the initial password for the new user. Share it with them through a secure channel — there is no way to view it again."
        onClose={handleModalClose}
      />
    </section>
  );
}
