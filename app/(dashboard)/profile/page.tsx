"use client";

import React, { useState, useEffect } from "react";
import { User, Mail, Save, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { authClient } from "@/lib/auth-client";
import { toast } from "sonner";

export default function ProfilePage() {
  const { data: session } = authClient.useSession();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");

  useEffect(() => {
    if (session?.user) {
      if (session.user.name) setName(session.user.name);
      if (session.user.email) setEmail(session.user.email);
      if (session.user.image) setAvatarUrl(session.user.image);
    }
  }, [session]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    toast.success("Profile updated successfully");
  };

  return (
    <div className="space-y-6 sm:space-y-8 animate-fade-in pb-16 max-w-3xl text-slate-900 dark:text-[#E2E4E9]">
      <div className="space-y-1.5">
        <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-[#1E2026] border border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] text-[11px] font-mono">
          <User className="w-3.5 h-3.5 text-emerald-600 dark:text-[#E2E4E9]" />
          <span>Account Credentials</span>
        </div>
        <h1 className="text-xl sm:text-2xl font-archivo font-bold tracking-tight text-slate-900 dark:text-[#E2E4E9]">
          User Profile
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 dark:text-[#9E9E9E]">
          Manage your display name, account email, and avatar photo across OverBranch.
        </p>
      </div>

      <Card className="p-6 sm:p-8 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] shadow-sm dark:shadow-none space-y-6">
        <div className="flex items-center gap-4">
          <Avatar className="w-16 h-16 sm:w-18 sm:h-18 border border-slate-200 dark:border-[#282A30] bg-slate-100 dark:bg-[#1A1C22] shrink-0">
            <AvatarImage src={avatarUrl} />
            <AvatarFallback className="bg-emerald-600 dark:bg-[#22242C] text-white dark:text-[#E2E4E9] font-mono font-bold text-base">
              {(name || 'U').slice(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1 space-y-1">
            <h2 className="text-base sm:text-lg font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] truncate">{name || "OverBranch User"}</h2>
            <p className="text-xs text-slate-500 dark:text-[#9E9E9E] font-mono truncate">{email || "user@example.com"}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 font-mono">
          <div className="space-y-1.5">
            <Label htmlFor="prof-name" className="text-xs font-medium text-slate-600 dark:text-[#9E9E9E] uppercase">
              Full Name / Co-Author Display Name
            </Label>
            <Input
              id="prof-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-10 text-xs font-mono border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#383B46]"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="prof-email" className="text-xs font-medium text-slate-600 dark:text-[#9E9E9E] uppercase">
              Account Email
            </Label>
            <Input
              id="prof-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-10 text-xs font-mono border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#383B46]"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="prof-avatar" className="text-xs font-medium text-slate-600 dark:text-[#9E9E9E] uppercase">
              Avatar Image URL
            </Label>
            <Input
              id="prof-avatar"
              value={avatarUrl}
              onChange={(e) => setAvatarUrl(e.target.value)}
              placeholder="https://..."
              className="h-10 text-xs font-mono border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#383B46]"
            />
          </div>

          <div className="pt-3 flex justify-end">
            <Button
              type="submit"
              className="h-9 px-5 bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold text-xs rounded-lg border border-emerald-600 dark:border-[#282A30] cursor-pointer flex items-center gap-2 shadow-sm"
            >
              <Save className="w-3.5 h-3.5 text-white dark:text-[#E2E4E9]" />
              <span>Save Changes</span>
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

