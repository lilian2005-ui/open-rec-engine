import { useEffect, useMemo, useState, type ReactNode } from "react";
import * as api from "./api";
import { AuthContext, type AuthState } from "./auth-context";
import type { User } from "./types";

/** Keeps "who is logged in" for the whole app. Wrap the app with it once. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // when the page opens, check if there is a saved login
  useEffect(() => {
    let cancelled = false;
    api
      .getCurrentUser()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login: async (email, password) => setUser(await api.login(email, password)),
      logout: async () => {
        await api.logout();
        setUser(null);
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}