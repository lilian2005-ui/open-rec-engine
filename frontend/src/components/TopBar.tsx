import { NavLink, useNavigate } from "react-router-dom";
import { USE_MOCK } from "../api";
import { useAuth } from "../useAuth";

const LINKS = [
  { to: "/jobs", label: "Jobs" },
  { to: "/leads", label: "Leads" },
  { to: "/settings", label: "Settings" },
];

/** The bar at the top of every screen except Login. */
export function TopBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="topbar">
      <span className="brand">Open Rec Engine</span>
      <nav>
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="topbar-user">
        {USE_MOCK && <span className="badge">MOCK DATA</span>}
        <span>{user?.email}</span>
        <button type="button" onClick={handleLogout}>
          Log out
        </button>
      </div>
    </header>
  );
}