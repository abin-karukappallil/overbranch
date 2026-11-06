"use client";

import React from "react";
import { MessageCircleQuestion, Pencil } from "lucide-react";

export type ChatMode = "ask" | "edit";

interface ChatModeToggleProps {
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  disabled?: boolean;
}

export function ChatModeToggle({ mode, onModeChange, disabled }: ChatModeToggleProps) {
  return (
    <div className="relative flex h-7 shrink-0 select-none items-center rounded-lg border border-ob-line bg-ob-raised p-0.5 font-mono text-xs">
      {/* Active background indicator */}
      <div
        className="absolute top-0.5 bottom-0.5 rounded-md bg-ob-card transition-all duration-150 ease-out"
        style={{
          left: mode === "ask" ? "2px" : "50%",
          width: "calc(50% - 2px)",
        }}
      />

      <button
        type="button"
        disabled={disabled}
        onClick={() => onModeChange("ask")}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") {
            e.preventDefault();
            onModeChange("edit");
          }
        }}
        className={`relative z-10 flex cursor-pointer items-center gap-1 rounded-md px-2.5 py-0.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          mode === "ask"
            ? "font-medium text-ob-text"
            : "text-ob-muted hover:text-ob-text"
        }`}
        title="Ask mode — answers questions without modifying document"
      >
        <MessageCircleQuestion className="size-3" />
        <span>Ask</span>
      </button>

      <button
        type="button"
        disabled={disabled}
        onClick={() => onModeChange("edit")}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") {
            e.preventDefault();
            onModeChange("ask");
          }
        }}
        className={`relative z-10 flex cursor-pointer items-center gap-1 rounded-md px-2.5 py-0.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          mode === "edit"
            ? "font-medium text-ob-text"
            : "text-ob-muted hover:text-ob-text"
        }`}
        title="Edit mode — proposes diff edits"
      >
        <Pencil className="size-3" />
        <span>Edit</span>
      </button>
    </div>
  );
}
