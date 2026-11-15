import { NavLink } from "react-router-dom";
import { useTheme } from "../hooks/useTheme";
import { useAuth } from "../useAuth";
import { Icon, type IconName } from "./Icon";

const LINKS: Array<{ to: string; label: string; icon: IconName; adminOnly?: boolean }> = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/jobs", label: "Jobs", icon: "jobs" },
  { to: "/leads", label: "Leads", icon: "leads" },
  { to: "/settings", label: "Settings", icon: "settings", adminOnly: true },
];

export function Sidebar() {
  const { user, isAdmin, logout } = useAuth();
  const { theme, toggle } = useTheme();
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo">❄</div>
        <div><b>Open Rec</b><small>by Simera</small></div>
      </div>
      <nav>
        {LINKS.filter((l) => !l.adminOnly || isAdmin).map((l) => (
          <NavLink key={l.to} to={l.to} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <Icon name={l.icon} />{l.label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <button className="nav-link btn-ghost" style={{ width: "100%", border: 0, background: "none", font: "inherit", cursor: "pointer" }} onClick={toggle}>
          <Icon name={theme === "dark" ? "sun" : "moon"} />{theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
        {user && (
          <div className="sidebar-user">
            <div className="avatar">{user.full_name.charAt(0).toUpperCase()}</div>
            <div className="who"><b>{user.full_name}</b><small>{user.role === "admin" ? "Admin" : "Reviewer"}</small></div>
            <button className="btn btn-ghost" onClick={logout} title="Log out" aria-label="Log out"><Icon name="logout" /></button>
          </div>
        )}
      </div>
    </aside>
  );
}
