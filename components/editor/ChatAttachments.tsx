"use client";

import React from "react";
import { AlertTriangle, FileText, Image as ImageIcon, Loader2, Paperclip, X } from "lucide-react";
import { ChatAttachment, describeAttachment } from "./useChatAttachments";

interface ChatAttachmentsProps {
  attachments: ChatAttachment[];
  maxFiles: number;
  onRemove: (attachment: ChatAttachment) => void;
  disabled?: boolean;
}

/** The files attached to the chat: one chip each, with what was found in it. */
export function ChatAttachments({ attachments, maxFiles, onRemove, disabled }: ChatAttachmentsProps) {
  if (attachments.length === 0) return null;
  const counted = attachments.filter((a) => a.status !== "error").length;

  return (
    <div className="mb-2 space-y-1">
      <div className="flex items-center justify-between px-0.5 text-[10px] font-mono text-slate-500 dark:text-[#8A8F98]">
        <span className="flex items-center gap-1">
          <Paperclip className="w-3 h-3" />
          Attached files
        </span>
        <span>
          {counted}/{maxFiles}
        </span>
      </div>
      <div className="max-h-32 overflow-y-auto ob-thin-scroll space-y-1">
        {attachments.map((a) => {
          const failed = a.status === "error";
          const Icon = a.status === "uploading" ? Loader2 : failed ? AlertTriangle : a.kind === "image" ? ImageIcon : FileText;
          return (
            <div
              key={a.id}
              className={`flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg border text-[11px] font-mono ${
                failed
                  ? "bg-red-50 dark:bg-[#EB5757]/10 border-red-200 dark:border-[#EB5757]/30 text-red-700 dark:text-[#F28B8B]"
                  : "bg-slate-100 dark:bg-[#141517] border-slate-200 dark:border-[#23252A] text-slate-900 dark:text-[#F7F8F8]"
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <Icon
                  className={`w-3.5 h-3.5 shrink-0 ${
                    a.status === "uploading"
                      ? "animate-spin text-slate-500 dark:text-[#8A8F98]"
                      : failed
                        ? "text-red-600 dark:text-[#EB5757]"
                        : "text-indigo-600 dark:text-[#5E6AD2]"
                  }`}
                />
                <div className="min-w-0">
                  <div className="truncate font-medium" title={a.filename}>
                    {a.filename}
                  </div>
                  <div className={`truncate text-[10px] ${failed ? "" : "text-slate-500 dark:text-[#8A8F98]"}`}>
                    {describeAttachment(a)}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => onRemove(a)}
                disabled={disabled || a.status === "uploading"}
                className="p-1 shrink-0 text-slate-400 dark:text-[#8A8F98] hover:text-red-500 dark:hover:text-[#EB5757] transition-colors rounded-md cursor-pointer disabled:opacity-40 disabled:cursor-default"
                title="Remove attachment"
                aria-label={`Remove ${a.filename}`}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
