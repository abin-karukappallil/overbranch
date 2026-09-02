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
    <div className="relative flex items-center h-7 rounded-lg bg-zinc-900 border border-zinc-800 p-0.5 select-none shrink-0">
      {/* Animated active indicator */}
      <div
        className="absolute top-0.5 bottom-0.5 rounded-md bg-[#00CC68]/20 border border-[#00CC68]/40 transition-all duration-200 ease-out"
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
        className={`relative z-10 flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[10px] font-mono font-bold transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
          mode === "ask"
            ? "text-[#00CC68]"
            : "text-zinc-500 hover:text-zinc-300"
        }`}
        title="Ask mode — AI answers questions without editing the document"
      >
        <MessageCircleQuestion className="w-3 h-3" />
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
        className={`relative z-10 flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[10px] font-mono font-bold transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
          mode === "edit"
            ? "text-[#00CC68]"
            : "text-zinc-500 hover:text-zinc-300"
        }`}
        title="Edit mode — AI edits your document with diff preview"
      >
        <Pencil className="w-3 h-3" />
        <span>Edit</span>
      </button>
    </div>
  );
}
