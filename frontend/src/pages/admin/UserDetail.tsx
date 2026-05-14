import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { PasswordOnceModal } from "@/components/admin/PasswordOnceModal";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type UserResponse = components["schemas"]["UserResponse"];
type Role = components["schemas"]["Role"];

const ROLES: Role[] = ["owner", "bookkeeper", "production", "sales", "viewer"];

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isOwner = useAuthStore((s) => s.user?.role === "owner");

  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<Role>("sales");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const [confirmDeact, setConfirmDeact] = useState(false);
  const [newPassword, setNewPassword] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    // The typed-paths helper doesn't yet interpolate `{user_id}`, so we
    // hit the raw axios client. The response shape is still validated by
    // the generated `UserResponse` type at call sites.
    apiClient
      .get<UserResponse>(`/api/v1/users/${id}`)
      .then((res) => {
        if (cancelled) return;
        setUser(res.data);
        setFullName(res.data.full_name);
        setRole(res.data.role);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load user.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function save() {
    if (!id) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await apiClient.patch<UserResponse>(`/api/v1/users/${id}`, {
        full_name: fullName,
        role,
      });
      setUser(res.data);
      setSaveMsg("Saved.");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Save failed.";
      setSaveMsg(detail);
    } finally {
      setSaving(false);
    }
  }

  async function doDeactivate() {
    if (!id) return;
    try {
      const res = await apiClient.post<UserResponse>(`/api/v1/users/${id}/deactivate`);
      setUser(res.data);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not deactivate.";
      setSaveMsg(detail);
    } finally {
      setConfirmDeact(false);
    }
  }

  async function doReactivate() {
    if (!id) return;
    try {
      const res = await apiClient.post<UserResponse>(`/api/v1/users/${id}/reactivate`);
      setUser(res.data);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not reactivate.";
      setSaveMsg(detail);
    }
  }

  async function doResetPassword() {
    if (!id) return;
    try {
      const res = await apiClient.post<{ generated_password: string }>(
        `/api/v1/users/${id}/reset-password`,
      );
      setNewPassword(res.data.generated_password);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not reset password.";
      setSaveMsg(detail);
    } finally {
      setConfirmReset(false);
    }
  }

  if (loading) return <p>Loading…</p>;
  if (error || !user)
    return (
      <div role="alert" className="text-destructive">
        {error ?? "User not found."}
      </div>
    );

  return (
    <section className="max-w-xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{user.email}</h1>
        <p className="text-sm text-muted-foreground">
          {user.is_active ? "Active" : "Inactive"} ·{" "}
          {user.last_login
            ? `Last login ${new Date(user.last_login).toLocaleString()}`
            : "No login recorded"}
        </p>
      </header>

      {isOwner ? (
        <fieldset className="space-y-3" data-testid="edit-form">
          <legend className="text-sm font-medium">Profile</legend>
          <label className="block text-sm">
            Full name
            <Input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="mt-1"
            />
          </label>
          <label className="block text-sm">
            Role
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate("/admin/users")}
            >
              Back
            </Button>
          </div>
          {saveMsg ? (
            <p role="status" data-testid="save-msg" className="text-sm">
              {saveMsg}
            </p>
          ) : null}
        </fieldset>
      ) : null}

      {isOwner ? (
        <section className="space-y-3 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Account actions</h2>
          <div className="flex flex-wrap gap-2">
            {user.is_active ? (
              <Button
                variant="destructive"
                onClick={() => setConfirmDeact(true)}
                data-testid="deactivate-btn"
              >
                Deactivate
              </Button>
            ) : (
              <Button onClick={doReactivate} data-testid="reactivate-btn">
                Reactivate
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => setConfirmReset(true)}
              data-testid="reset-pwd-btn"
            >
              Reset password
            </Button>
          </div>
        </section>
      ) : null}

      <Dialog open={confirmDeact} onOpenChange={setConfirmDeact}>
        <DialogContent>
          <DialogTitle>Deactivate {user.email}?</DialogTitle>
          <DialogDescription>
            They will be signed out everywhere and won&rsquo;t be able to log in
            until reactivated.
          </DialogDescription>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirmDeact(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={doDeactivate}
              data-testid="confirm-deactivate"
            >
              Deactivate
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmReset} onOpenChange={setConfirmReset}>
        <DialogContent>
          <DialogTitle>Reset password for {user.email}?</DialogTitle>
          <DialogDescription>
            A new one-time password will be generated. The user will be signed
            out everywhere.
          </DialogDescription>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirmReset(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={doResetPassword}
              data-testid="confirm-reset"
            >
              Reset password
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <PasswordOnceModal
        open={newPassword !== null}
        password={newPassword ?? ""}
        title="Password reset"
        description="Share this new one-time password through a secure channel. There is no way to retrieve it again."
        onClose={() => setNewPassword(null)}
      />
    </section>
  );
}
