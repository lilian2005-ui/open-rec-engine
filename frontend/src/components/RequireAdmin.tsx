import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../useAuth";

/** Settings is for admins. A reviewer who opens the link goes back to Jobs.
 *  This is only for the look: the backend answers 403 anyway. */
export function RequireAdmin() {
  const { isAdmin } = useAuth();
  return isAdmin ? <Outlet /> : <Navigate to="/jobs" replace />;
}
