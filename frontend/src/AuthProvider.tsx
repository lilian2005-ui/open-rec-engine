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

  // any 401 from the backend (expired token) logs the user out -> RequireAuth shows Login
  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener(api.UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(api.UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      isAdmin: user?.role === "admin",
      login: async (email, password) => setUser(await api.login(email, password)),
      // registering does not log in: the backend gives no token, so the user logs in after
      register: async (fullName, email, password) => {
        await api.register(fullName, email, password);
      },
      logout: async () => {
        await api.logout();
        setUser(null);
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
