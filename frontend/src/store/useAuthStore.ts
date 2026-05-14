import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type Role =
  | "owner"
  | "bookkeeper"
  | "production"
  | "sales"
  | "viewer";

export interface AuthUser {
  id: string;
  email: string;
  role: Role;
}

export interface AuthSession {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
}

export interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  setSession: (session: AuthSession) => void;
  clearSession: () => void;
}

const noopStorage: Storage = {
  length: 0,
  clear: () => {},
  getItem: () => null,
  key: () => null,
  removeItem: () => {},
  setItem: () => {},
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setSession: (session) =>
        set({
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          user: session.user,
        }),
      clearSession: () =>
        set({ accessToken: null, refreshToken: null, user: null }),
    }),
    {
      name: "voxel-ledger.auth",
      storage: createJSONStorage(() =>
        typeof window === "undefined" ? noopStorage : window.localStorage,
      ),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    },
  ),
);
