"use client";

import * as React from "react";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import {
  Search,
  Plus,
  FolderGit2,
  User,
  LayoutDashboard,
  Zap,
  LogOut,
  Moon,
  Sun,
  FileCode2,
} from "lucide-react";
import { useTheme } from "next-themes";

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
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-black/80 backdrop-blur-md animate-fade-in font-sans">
      <div
        className="fixed inset-0"
        onClick={() => onOpenChange(false)}
      />
      <div className="relative w-full max-w-2xl rounded-2xl border border-zinc-800 bg-zinc-900 text-white shadow-2xl overflow-hidden z-10 font-mono">
        <Command className="w-full">
          <div className="flex items-center px-4 border-b border-zinc-800">
            <Search className="w-5 h-5 text-[#00CC68] mr-3 shrink-0" />
            <Command.Input
              autoFocus
              placeholder="Type a command or search projects, templates, settings..."
              className="w-full h-14 bg-transparent text-white placeholder:text-zinc-500 text-sm outline-none font-mono"
            />
            <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs font-mono text-zinc-400 bg-zinc-950 rounded border border-zinc-800">
              ESC
            </kbd>
          </div>

          <Command.List className="max-h-[340px] overflow-y-auto p-2 space-y-1">
            <Command.Empty className="p-6 text-center text-sm text-zinc-400 font-sans">
              No matching commands or projects found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="px-2 py-1.5 text-xs font-bold text-zinc-500 uppercase tracking-wider font-mono">
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/dashboard"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs cursor-pointer hover:bg-zinc-800 hover:text-white transition-colors"
              >
                <LayoutDashboard className="w-4 h-4 text-[#00CC68]" />
                <span>Go to Overview Dashboard</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs cursor-pointer hover:bg-zinc-800 hover:text-white transition-colors"
              >
                <FileCode2 className="w-4 h-4 text-[#00CC68]" />
                <span>Projects List</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/profile"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs cursor-pointer hover:bg-zinc-800 hover:text-white transition-colors"
              >
                <User className="w-4 h-4 text-[#00CC68]" />
                <span>User Profile</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Projects & Actions" className="px-2 py-1.5 text-xs font-bold text-zinc-500 uppercase tracking-wider font-mono mt-2">
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs cursor-pointer hover:bg-zinc-800 hover:text-white transition-colors"
              >
                <Plus className="w-4 h-4 text-[#00CC68]" />
                <span>Create New LaTeX Project</span>
                <span className="ml-auto text-xs text-[#00CC68] font-mono font-bold">New</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs cursor-pointer hover:bg-zinc-800 hover:text-white transition-colors"
              >
                <FolderGit2 className="w-4 h-4 text-[#00CC68]" />
                <span>Manage Workspace Projects</span>
                <span className="ml-auto text-xs text-[#00CC68] font-mono font-bold">View All</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Preferences" className="px-2 py-1.5 text-xs font-bold text-zinc-500 uppercase tracking-wider font-mono mt-2">
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/login"))}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs cursor-pointer hover:bg-zinc-800 text-rose-400 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </Command.Item>
            </Command.Group>
          </Command.List>

          <div className="p-3 border-t border-zinc-800 bg-zinc-950 flex items-center justify-between text-xs text-zinc-400">
            <div className="flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-[#00CC68]" />
              <span>OverBranch Command Palette</span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span>↑↓ Navigate</span>
              <span>↵ Select</span>
            </div>
          </div>
        </Command>
      </div>
    </div>
  );
}
