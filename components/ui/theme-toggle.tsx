"use client";

import * as React from "react";
import { Moon, Sun, Laptop } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" className={`h-9 w-9 rounded-lg ${className}`}>
        <Sun className="h-4 w-4 text-muted-foreground" />
      </Button>
    );
  }

  const cycleTheme = () => {
    if (theme === "dark") setTheme("light");
    else if (theme === "light") setTheme("system");
    else setTheme("dark");
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={cycleTheme}
      className={`h-9 w-9 rounded-lg transition-all hover:bg-accent/60 relative ${className}`}
      title={`Current theme: ${theme}. Click to switch.`}
    >
      {theme === "dark" && <Moon className="h-4 w-4 text-indigo-400 transition-all scale-100 rotate-0" />}
      {theme === "light" && <Sun className="h-4 w-4 text-amber-500 transition-all scale-100 rotate-0" />}
      {theme === "system" && <Laptop className="h-4 w-4 text-slate-400 transition-all scale-100 rotate-0" />}
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}
