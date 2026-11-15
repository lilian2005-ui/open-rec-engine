import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";

/** Sidebar + the screen of the current page. */
export function Layout() {
  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        <div className="main-inner"><Outlet /></div>
      </main>
    </div>
  );
}
