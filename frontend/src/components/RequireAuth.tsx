import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../useAuth";

/** Every screen except Login needs a logged-in user (FR-36). */
export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <p className="status">Loading…</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}