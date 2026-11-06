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
  LogOut,
  FileCode2,
} from "lucide-react";

const GROUP =
  "px-1 pb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-ob-muted";
const ROW =
  "flex h-9 items-center gap-2.5 rounded-sm px-2 text-[13px] cursor-pointer text-ob-text-2 transition-colors data-[selected=true]:bg-ob-raised data-[selected=true]:text-ob-text";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const router = useRouter();

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
    <div className="fixed inset-0 z-50 flex animate-in items-start justify-center bg-black/60 px-4 pt-20 duration-150 fade-in">
      <div
        className="fixed inset-0"
        onClick={() => onOpenChange(false)}
      />
      <div className="relative z-10 w-full max-w-xl overflow-hidden rounded-xl border border-ob-line bg-ob-card text-ob-text shadow-[0_16px_48px_rgba(0,0,0,0.32)]">
        <Command className="w-full">
          <div className="flex items-center border-b border-ob-line px-4">
            <Search className="mr-2.5 size-4 shrink-0 text-ob-muted" />
            <Command.Input
              autoFocus
              placeholder="Search"
              className="h-11 w-full bg-transparent text-sm text-ob-text outline-none placeholder:text-ob-muted"
            />
            <kbd className="hidden items-center rounded-sm border border-ob-line px-1 font-mono text-xs leading-[18px] text-ob-muted sm:inline-flex">
              Esc
            </kbd>
          </div>

          <Command.List className="max-h-[320px] overflow-y-auto p-1">
            <Command.Empty className="p-6 text-center text-[13px] text-ob-muted">
              Nothing matches that
            </Command.Empty>

            <Command.Group heading="Navigation" className={GROUP}>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/dashboard"))}
                className={ROW}
              >
                <LayoutDashboard className="size-4 text-ob-muted" />
                <span>Overview</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className={ROW}
              >
                <FileCode2 className="size-4 text-ob-muted" />
                <span>Projects</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/profile"))}
                className={ROW}
              >
                <User className="size-4 text-ob-muted" />
                <span>Profile and settings</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Actions" className={GROUP}>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className={ROW}
              >
                <Plus className="size-4 text-ob-muted" />
                <span>New LaTeX project</span>
              </Command.Item>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/projects"))}
                className={ROW}
              >
                <FolderGit2 className="size-4 text-ob-muted" />
                <span>Manage projects</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Account" className={GROUP}>
              <Command.Item
                onSelect={() => handleSelect(() => router.push("/login"))}
                className={ROW}
              >
                <LogOut className="size-4 text-ob-muted" />
                <span>Sign out</span>
              </Command.Item>
            </Command.Group>
          </Command.List>

          <div className="flex items-center justify-end gap-3 border-t border-ob-line px-4 py-2 font-mono text-xs text-ob-muted">
            <span>↑↓ Navigate</span>
            <span>↵ Select</span>
          </div>
        </Command>
      </div>
    </div>
  );
}
