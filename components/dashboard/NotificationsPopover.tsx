"use client";

import React, { useState } from "react";
import { Bell, Check, GitCommit, Sparkles, ShieldCheck, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";

const initialNotifications = [
  {
    id: "1",
    title: "Database Migration Completed",
    description: "Supabase tables generated for Better Auth core schema.",
    time: "5m ago",
    read: false,
    icon: Cpu,
    color: "text-indigo-400",
  },
  {
    id: "2",
    title: "New Project Created",
    description: "overbranch-frontend initialized with Next.js 15 App Router.",
    time: "1h ago",
    read: false,
    icon: GitCommit,
    color: "text-cyan-400",
  },
  {
    id: "3",
    title: "Session Verified",
    description: "Better Auth OAuth token refreshed successfully.",
    time: "3h ago",
    read: true,
    icon: ShieldCheck,
    color: "text-emerald-400",
  },
];

export function NotificationsPopover() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(initialNotifications);

  const unreadCount = items.filter((i) => !i.read).length;

  const markAllRead = () => {
    setItems(items.map((i) => ({ ...i, read: true })));
  };

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setOpen(!open)}
        className="h-9 w-9 rounded-xl hover:bg-accent relative"
        title="Notifications"
      >
        <Bell className="w-4 h-4 text-muted-foreground" />
        {unreadCount > 0 && (
          <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
        )}
      </Button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-11 z-50 w-80 sm:w-96 rounded-2xl border border-border/70 bg-card/95 backdrop-blur-xl shadow-2xl p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-border/40 pb-3">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-foreground">Notifications</span>
                {unreadCount > 0 && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-indigo-500/20 text-indigo-400 font-mono">
                    {unreadCount} new
                  </span>
                )}
              </div>
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="text-xs text-indigo-400 hover:underline flex items-center gap-1"
                >
                  <Check className="w-3.5 h-3.5" /> Mark all read
                </button>
              )}
            </div>

            <div className="space-y-2 max-h-72 overflow-y-auto">
              {items.map((item) => {
                const Icon = item.icon;
                return (
                  <div
                    key={item.id}
                    className={`p-3 rounded-xl border transition-all ${
                      item.read
                        ? "border-border/30 bg-muted/20 opacity-80"
                        : "border-indigo-500/30 bg-indigo-500/5 shadow-xs"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="p-2 rounded-lg bg-muted/60 shrink-0 mt-0.5">
                        <Icon className={`w-4 h-4 ${item.color}`} />
                      </div>
                      <div className="space-y-1 text-xs">
                        <div className="flex items-center justify-between font-semibold text-foreground">
                          <span>{item.title}</span>
                          <span className="text-[10px] text-muted-foreground font-mono">{item.time}</span>
                        </div>
                        <p className="text-muted-foreground leading-relaxed">{item.description}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
