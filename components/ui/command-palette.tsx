"use client";

import * as React from "react";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import {
  Search,
  Code2,
  Plus,
  FolderGit2,
  Settings,
  User,
  LayoutDashboard,
  Sparkles,
  Terminal,
  LogOut,
  Moon,
  Sun,
  FileCode2,
  BookOpen,
  CreditCard,
  Users,
} from "lucide-react";
import { useTheme } from "next-themes";
import { toast } from "sonner";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const router = useRouter();
  const { theme, setTheme } = useTheme();

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open, onOpenChange]);

  if (!open) return null;

  const handleSelect = (callback: () => void) => {
    onOpenChange(false);
    callback();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-background/80 backdrop-blur-md animate-fade-in">
      <div
        className="fixed inset-0"
        onClick={() => onOpenChange(false)}
      />
      <div className="relative w-full max-w-2xl rounded-2xl border border-border/60 bg-card/90 backdrop-blur-xl shadow-2xl overflow-hidden z-10">
        <Command className="w-full">
          <div className="flex items-center px-4 border-b border-border/40">
            <Search className="w-5 h-5 text-muted-foreground mr-3 shrink-0" />
            <Command.Input
              autoFocus
              placeholder="Type a command or search projects, templates, settings..."
              className="w-full h-14 bg-transparent text-foreground placeholder:text-muted-foreground text-base outline-none"
            />
            <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs font-mono text-muted-foreground bg-muted rounded border border-border/40">
              ESC
            </kbd>
          </div>

          <Command.List className="max-h-[340px] overflow-y-auto p-2 space-y-1">
            <Command.Empty className="p-6 text-center text-sm text-muted-foreground">
              No matching commands or projects found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="px-2 py-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/dashboard"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <LayoutDashboard className="w-4 h-4 text-indigo-400" />
                <span>Go to Overview Dashboard</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <FileCode2 className="w-4 h-4 text-indigo-400" />
                <span>Projects List</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/profile"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <User className="w-4 h-4 text-indigo-400" />
                <span>User Profile</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Projects & Quick Actions" className="px-2 py-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider mt-2">
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/editor"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <Plus className="w-4 h-4 text-emerald-400" />
                <span>Create New LaTeX Project</span>
                <span className="ml-auto text-xs text-emerald-400 font-mono">Editor</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <FolderGit2 className="w-4 h-4 text-cyan-400" />
                <span>Manage Workspace Projects</span>
                <span className="ml-auto text-xs text-cyan-400 font-mono">View All</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Preferences" className="px-2 py-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider mt-2">
              <Command.Item
                onSelect={() => handleSelect(() => setTheme(theme === "dark" ? "light" : "dark"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                {theme === "dark" ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-400" />}
                <span>Toggle Theme ({theme === "dark" ? "Light" : "Dark"})</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/login"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm cursor-pointer hover:bg-accent text-rose-500 hover:text-rose-400 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </Command.Item>
            </Command.Group>
          </Command.List>

          <div className="p-3 border-t border-border/40 bg-muted/40 flex items-center justify-between text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              <span>OverBranch Command Matrix</span>
            </div>
            <div className="flex items-center gap-3 font-mono">
              <span>↑↓ Navigate</span>
              <span>↵ Select</span>
            </div>
          </div>
        </Command>
      </div>
    </div>
  );
}
