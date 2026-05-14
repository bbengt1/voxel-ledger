import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { HomePage } from "@/pages/Home";
import { LoginPage } from "@/pages/Login";
import { UserCreatePage } from "@/pages/admin/UserCreate";
import { UserDetailPage } from "@/pages/admin/UserDetail";
import { UsersListPage } from "@/pages/admin/UsersList";
import { MaterialCreatePage } from "@/pages/catalog/MaterialCreate";
import { MaterialDetailPage } from "@/pages/catalog/MaterialDetail";
import { MaterialsListPage } from "@/pages/catalog/MaterialsList";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppShell>
              <HomePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/admin/users"
        element={
          <RequireAuth>
            <AppShell>
              <UsersListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/admin/users/new"
        element={
          <RequireAuth>
            <AppShell>
              <UserCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/admin/users/:id"
        element={
          <RequireAuth>
            <AppShell>
              <UserDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/materials"
        element={
          <RequireAuth>
            <AppShell>
              <MaterialsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/materials/new"
        element={
          <RequireAuth>
            <AppShell>
              <MaterialCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/materials/:id"
        element={
          <RequireAuth>
            <AppShell>
              <MaterialDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
