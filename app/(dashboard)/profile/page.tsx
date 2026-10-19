"use client";

import React, { useEffect } from "react";
import { User, Mail } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { authClient } from "@/lib/auth-client";

export default function ProfilePage() {
  const { data: session } = authClient.useSession();

  const user = session?.user;
  const name = user?.name || "User";
  const email = user?.email || "";
  const avatarUrl = user?.image || "";

  useEffect(() => {
    document.title = "OverBranch | Profile";
  }, []);

  return (
    <div className="space-y-6 sm:space-y-8 animate-fade-in pb-16 max-w-2xl text-slate-900 dark:text-[#E2E4E9]">
      <div className="space-y-1">
        <h1 className="text-xl sm:text-2xl font-archivo font-bold tracking-tight text-slate-900 dark:text-[#E2E4E9]">
          User Profile
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 dark:text-[#9E9E9E]">
          Your account details in OverBranch.
        </p>
      </div>

      <Card className="p-6 sm:p-8 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] shadow-sm dark:shadow-none space-y-6">
        {/* Profile Avatar & Header */}
        <div className="flex items-center gap-4 sm:gap-5">
          <Avatar className="w-16 h-16 sm:w-20 sm:h-20 border border-slate-200 dark:border-[#282A30] bg-slate-100 dark:bg-[#1A1C22] shrink-0">
            {avatarUrl && (
              <AvatarImage
                src={avatarUrl}
                referrerPolicy="no-referrer"
                alt={name}
              />
            )}
            <AvatarFallback className="bg-emerald-600 dark:bg-[#22242C] text-white dark:text-[#E2E4E9] font-archivo font-bold text-lg sm:text-xl">
              {(name || "U").slice(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>

          <div className="min-w-0 flex-1 space-y-1">
            <h2 className="text-lg sm:text-xl font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] truncate">
              {name}
            </h2>
            <p className="text-xs sm:text-sm text-slate-500 dark:text-[#9E9E9E] font-mono truncate">
              {email}
            </p>
          </div>
        </div>

        {/* Read-only info fields */}
        <div className="space-y-4 pt-2 border-t border-slate-100 dark:border-[#202228] font-mono">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-500 dark:text-[#8A8F98] uppercase tracking-wider flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-slate-400 dark:text-[#6A707E]" />
              <span>Full Name</span>
            </label>
            <div className="h-10 px-3 flex items-center text-xs border border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] rounded-lg">
              {name}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-500 dark:text-[#8A8F98] uppercase tracking-wider flex items-center gap-1.5">
              <Mail className="w-3.5 h-3.5 text-slate-400 dark:text-[#6A707E]" />
              <span>Email Address</span>
            </label>
            <div className="h-10 px-3 flex items-center text-xs border border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] rounded-lg">
              {email}
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
