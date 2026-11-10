import { Outlet } from "react-router-dom";
import { TopBar } from "./TopBar";

/** Top bar + the screen of the current page. */
export function Layout() {
  return (
    <>
      <TopBar />
      <main className="page">
        <Outlet />
      </main>
    </>
  );
}