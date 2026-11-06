"use client";

import React, { useEffect } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { authClient } from "@/lib/auth-client";
import { initialsOf } from "@/lib/initials";

export default function ProfilePage() {
  const { data: session } = authClient.useSession();

  const user = session?.user;
  const name = user?.name || user?.email?.split("@")[0] || "User";
  const email = user?.email || "";
  const avatarUrl = user?.image || "";

  useEffect(() => {
    document.title = "OverBranch | Profile";
  }, []);

  return (
    <div className="ob-enter flex max-w-2xl flex-col gap-8 pb-16">
      <header className="flex flex-col gap-2">
        <h1 className="font-ob-title text-[32px] leading-[1.15] font-normal text-ob-text">Profile</h1>
        <p className="text-sm leading-[22px] text-ob-text-2">
          Your account identity and workspace credentials
        </p>
      </header>

      <section className="flex flex-col gap-6 rounded-xl border border-ob-line bg-ob-card p-6">
        {/* User identifier row */}
        <div className="flex items-center gap-4">
          <Avatar className="size-14 rounded-xl border border-ob-line">
            {avatarUrl && (
              <AvatarImage src={avatarUrl} referrerPolicy="no-referrer" alt={name} />
            )}
            <AvatarFallback className="rounded-xl bg-ob-raised text-base font-medium text-ob-text-2">
              {initialsOf(name)}
            </AvatarFallback>
          </Avatar>

          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <h2 className="truncate text-base font-medium text-ob-text">{name}</h2>
            <p className="truncate font-mono text-xs text-ob-muted">{email}</p>
          </div>
        </div>

        {/* Read-only account fields */}
        <div className="flex flex-col gap-4 border-t border-ob-line pt-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-ob-text-2">Full name</label>
            <div className="flex h-9 items-center rounded-lg border border-ob-line bg-ob-raised px-3 text-sm text-ob-text select-text">
              {name}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-ob-text-2">Email address</label>
            <div className="flex h-9 items-center rounded-lg border border-ob-line bg-ob-raised px-3 font-mono text-sm text-ob-text select-text">
              {email}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
