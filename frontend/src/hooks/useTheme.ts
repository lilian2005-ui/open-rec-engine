import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const KEY = "openrec_theme";

function saved(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** Light / dark mode, remembered in this browser only. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(saved);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* private window: not remembered */
    }
  }, [theme]);
  return { theme, toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")) };
}
