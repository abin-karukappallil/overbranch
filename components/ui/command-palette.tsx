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
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-black/75 backdrop-blur-sm animate-fade-in font-sans">
      <div
        className="fixed inset-0"
        onClick={() => onOpenChange(false)}
      />
      <div className="relative w-full max-w-xl rounded-xl border border-[#23252A] bg-[#0F1011] text-[#F7F8F8] shadow-2xl overflow-hidden z-10 font-sans">
        <Command className="w-full">
          <div className="flex items-center px-4 border-b border-[#23252A] bg-[#141517]">
            <Search className="w-4 h-4 text-[#5E6AD2] mr-3 shrink-0" />
            <Command.Input
              autoFocus
              placeholder="Search actions, projects, templates, settings..."
              className="w-full h-11 bg-transparent text-[#F7F8F8] placeholder:text-[#62666D] text-xs outline-none font-sans"
            />
            <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono text-[#8A8F98] bg-[#08090A] rounded border border-[#23252A]">
              ESC
            </kbd>
          </div>

          <Command.List className="max-h-[300px] overflow-y-auto p-2 space-y-1">
            <Command.Empty className="p-6 text-center text-xs text-[#62666D] font-sans">
              No matching commands or projects found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="px-2 py-1 text-[10px] font-medium text-[#8A8F98] uppercase tracking-wider">
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/dashboard"))}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs cursor-pointer hover:bg-[#141517] text-[#8A8F98] hover:text-[#F7F8F8] transition-colors"
              >
                <LayoutDashboard className="w-3.5 h-3.5 text-[#5E6AD2]" />
                <span>Overview Dashboard</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs cursor-pointer hover:bg-[#141517] text-[#8A8F98] hover:text-[#F7F8F8] transition-colors"
              >
                <FileCode2 className="w-3.5 h-3.5 text-[#5E6AD2]" />
                <span>Projects List</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/profile"))}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs cursor-pointer hover:bg-[#141517] text-[#8A8F98] hover:text-[#F7F8F8] transition-colors"
              >
                <User className="w-3.5 h-3.5 text-[#5E6AD2]" />
                <span>User Profile & Settings</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Actions" className="px-2 py-1 text-[10px] font-medium text-[#8A8F98] uppercase tracking-wider mt-1.5">
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs cursor-pointer hover:bg-[#141517] text-[#8A8F98] hover:text-[#F7F8F8] transition-colors"
              >
                <Plus className="w-3.5 h-3.5 text-[#5E6AD2]" />
                <span>Create New LaTeX Project</span>
                <span className="ml-auto text-[10px] text-[#5E6AD2] font-mono font-medium">New</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs cursor-pointer hover:bg-[#141517] text-[#8A8F98] hover:text-[#F7F8F8] transition-colors"
              >
                <FolderGit2 className="w-3.5 h-3.5 text-[#5E6AD2]" />
                <span>Manage Workspace Projects</span>
                <span className="ml-auto text-[10px] text-[#8A8F98] font-mono">View All</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Account" className="px-2 py-1 text-[10px] font-medium text-[#8A8F98] uppercase tracking-wider mt-1.5">
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/login"))}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs cursor-pointer hover:bg-[#141517] text-[#EB5757] transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign Out</span>
              </Command.Item>
            </Command.Group>
          </Command.List>

          <div className="px-3.5 py-2 border-t border-[#23252A] bg-[#08090A] flex items-center justify-between text-xs text-[#8A8F98]">
            <div className="flex items-center gap-1.5">
              <Zap className="w-3 h-3 text-[#5E6AD2]" />
              <span className="text-[11px]">Command Palette</span>
            </div>
            <div className="flex items-center gap-2.5 font-mono text-[10px] text-[#62666D]">
              <span>↑↓ Navigate</span>
              <span>↵ Select</span>
            </div>
          </div>
        </Command>
      </div>
    </div>
  );
}
