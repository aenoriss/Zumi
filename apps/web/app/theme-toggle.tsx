"use client";
import { useEffect, useState } from "react";
import { Button } from "@zumi/ui";

type Theme = "paper" | "midnight";

/** Paper / Midnight switch. Persists per browser; the server renders Paper. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("paper");

  useEffect(() => {
    let saved: Theme | null = null;
    try {
      saved = localStorage.getItem("zumi-theme") as Theme | null;
    } catch {}
    if (saved === "midnight") setTheme("midnight");
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("zumi-theme", theme);
    } catch {}
  }, [theme]);

  return (
    <Button variant="ghost" size="sm" aria-pressed={theme === "midnight"} onClick={() => setTheme(theme === "paper" ? "midnight" : "paper")}>
      {theme === "paper" ? "Midnight" : "Paper"}
    </Button>
  );
}
