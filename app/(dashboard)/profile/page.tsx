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
    toast.success("Profile customization updated successfully");
  };

  return (
    <div className="space-y-6 sm:space-y-8 animate-fade-in pb-12 max-w-3xl font-sans text-zinc-100">
      <div className="space-y-1.5">
        <h1 className="text-xl sm:text-3xl font-archivo font-black uppercase tracking-tight text-white">
          User Profile Settings
        </h1>
        <p className="text-xs sm:text-sm text-zinc-400">
          Manage your display name, account email, and avatar photo across OverBranch.
        </p>
      </div>

      <Card className="p-6 sm:p-8 rounded-2xl border border-zinc-800 bg-zinc-900 shadow-xl space-y-6">
        <div className="flex items-center gap-4">
          <Avatar className="w-16 h-16 sm:w-20 sm:h-20 border-2 border-[#00CC68] shrink-0 shadow-lg">
            <AvatarImage src={avatarUrl} />
            <AvatarFallback className="bg-[#00CC68] text-black font-archivo font-bold text-lg">
              {(name || 'U').slice(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1 space-y-1">
            <h2 className="text-lg sm:text-xl font-archivo font-bold text-white truncate">{name || "OverBranch User"}</h2>
            <p className="text-xs text-[#00CC68] font-mono truncate">{email || "user@example.com"}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 font-mono">
          <div className="space-y-2">
            <Label htmlFor="prof-name" className="text-xs font-bold text-zinc-400 uppercase">
              Full Name / Co-Author Display Name
            </Label>
            <Input
              id="prof-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-11 text-xs font-mono border-zinc-800 bg-zinc-950 text-white focus-visible:ring-2 focus-visible:ring-[#00CC68]"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prof-email" className="text-xs font-bold text-zinc-400 uppercase">
              Account Email
            </Label>
            <Input
              id="prof-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 text-xs font-mono border-zinc-800 bg-zinc-950 text-white focus-visible:ring-2 focus-visible:ring-[#00CC68]"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prof-avatar" className="text-xs font-bold text-zinc-400 uppercase">
              Avatar Image URL
            </Label>
            <Input
              id="prof-avatar"
              value={avatarUrl}
              onChange={(e) => setAvatarUrl(e.target.value)}
              placeholder="https://..."
              className="h-11 text-xs font-mono border-zinc-800 bg-zinc-950 text-white focus-visible:ring-2 focus-visible:ring-[#00CC68]"
            />
          </div>

          <div className="pt-4 flex justify-end">
            <Button
              type="submit"
              className="h-10 px-6 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider rounded-xl border border-black shadow-[3px_3px_0px_0px_#000000] cursor-pointer"
            >
              <Save className="w-4 h-4 mr-2 text-black" />
              Save Profile
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
