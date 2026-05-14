import axios from "axios";
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Form, FormField } from "@/components/form/Form";
import { useAuthStore } from "@/store/useAuthStore";
import type { components } from "@/api/types";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

type LoginValues = z.infer<typeof loginSchema>;

type TokenPair = components["schemas"]["TokenPair"];
type MeResponse = components["schemas"]["MeResponse"];

const GENERIC_ERROR = "Invalid email or password.";
const NETWORK_ERROR = "Unable to reach the server. Try again.";

function LoginFields({ submitting }: { submitting: boolean }) {
  const { register } = useFormContext<LoginValues>();
  return (
    <>
      <FormField name="email" label="Email">
        <Input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          disabled={submitting}
          {...register("email")}
        />
      </FormField>
      <FormField name="password" label="Password">
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          disabled={submitting}
          {...register("password")}
        />
      </FormField>
    </>
  );
}

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const nextParam = searchParams.get("next");
  const nextPath = nextParam && nextParam.startsWith("/") ? nextParam : "/";

  const onSubmit = async (values: LoginValues) => {
    setFormError(null);
    setSubmitting(true);
    try {
      const loginRes = await apiClient.post<TokenPair>(
        "/api/v1/auth/login",
        values,
      );
      const tokens = loginRes.data;

      // Fetch the authenticated user. The bearer header is attached by the
      // interceptor once we set the session — so set it first, then call /me.
      // We pass the token through `Authorization` directly here to avoid a
      // race with persist middleware writes.
      const meRes = await apiClient.get<MeResponse>("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      });
      const me = meRes.data;

      setSession({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        user: {
          id: me.id,
          email: me.email,
          role: me.role,
          full_name: me.full_name,
        },
      });

      navigate(nextPath, { replace: true });
    } catch (err) {
      if (axios.isAxiosError(err)) {
        if (err.response?.status === 401) {
          setFormError(GENERIC_ERROR);
        } else if (!err.response) {
          setFormError(NETWORK_ERROR);
        } else {
          // 422 from validation, etc — keep the generic message to avoid
          // field-level enumeration leakage.
          setFormError(GENERIC_ERROR);
        }
      } else {
        setFormError(NETWORK_ERROR);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <section
        aria-labelledby="login-heading"
        className="w-full max-w-sm rounded-lg border border-border bg-background p-6 shadow-sm"
      >
        <h1
          id="login-heading"
          className="text-2xl font-semibold tracking-tight"
        >
          Sign in
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Use your Voxel Ledger account.
        </p>

        <Form
          schema={loginSchema}
          defaultValues={{ email: "", password: "" }}
          onSubmit={onSubmit}
          className="mt-6"
        >
          <LoginFields submitting={submitting} />
          {formError ? (
            <p
              role="alert"
              data-testid="login-error"
              className="text-sm text-destructive"
            >
              {formError}
            </p>
          ) : null}
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </Form>
      </section>
    </main>
  );
}
