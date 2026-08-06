"use client";

import React, { useState } from "react";
import { Users, UserPlus, Shield, Sparkles, Check, Copy, Settings, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { toast } from "sonner";

const mockMembers = [
  { id: "mem-1", name: "Dr. Alice Vance", email: "alice@overbranch.dev", role: "Owner", avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80" },
  { id: "mem-2", name: "Prof. Bob Chen", email: "bob@stanford.edu", role: "Admin", avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80" },
  { id: "mem-3", name: "Carol Zhang", email: "carol@overbranch.dev", role: "Member", avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80" },
];

export default function WorkspacesPage() {
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("Member");
  const [members, setMembers] = useState(mockMembers);

  const handleInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail) return;
    const newM = {
      id: `mem-${Date.now()}`,
      name: inviteEmail.split("@")[0],
      email: inviteEmail,
      role: inviteRole,
      avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80",
    };
    setMembers([...members, newM]);
    setInviteEmail("");
    toast.success(`Invitation sent to ${inviteEmail}`);
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
            Workspace & Team Management
          </h1>
          <p className="text-sm text-muted-foreground">
            Stanford & OverBranch Research Team — 12 Researchers
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-7 space-y-6">
          <Card className="p-6 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl space-y-6">
            <div className="flex items-center justify-between border-b border-border/40 pb-4">
              <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                <Users className="w-5 h-5 text-indigo-400" />
                Team Members ({members.length})
              </h2>
            </div>

            <div className="space-y-3">
              {members.map((m) => (
                <div key={m.id} className="p-3.5 rounded-xl border border-border/40 bg-muted/20 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <Avatar className="w-9 h-9">
                      <AvatarImage src={m.avatar} />
                      <AvatarFallback>{m.name.slice(0, 2)}</AvatarFallback>
                    </Avatar>
                    <div>
                      <span className="font-bold text-foreground block">{m.name}</span>
                      <span className="text-muted-foreground font-mono text-[11px]">{m.email}</span>
                    </div>
                  </div>
                  <span className="px-2.5 py-1 rounded-full bg-indigo-500/10 text-indigo-400 font-mono font-bold text-[11px]">
                    {m.role}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="lg:col-span-5 space-y-6">
          <Card className="p-6 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl space-y-4">
            <div className="flex items-center gap-2 text-indigo-400 font-bold text-sm">
              <UserPlus className="w-4 h-4" />
              Invite Researcher
            </div>
            <p className="text-xs text-muted-foreground">
              Send an email invitation link to add co-authors to this workspace.
            </p>

            <form onSubmit={handleInvite} className="space-y-3">
              <Input
                type="email"
                placeholder="co-author@university.edu"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                className="h-10 text-xs"
              />

              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="w-full h-10 px-3 text-xs rounded-lg border border-border/60 bg-background text-foreground outline-none font-mono"
              >
                <option value="Member">Member (Read & Write)</option>
                <option value="Admin">Admin (Full Workspace Management)</option>
              </select>

              <Button type="submit" className="w-full bg-indigo-600 text-white rounded-xl h-10 text-xs">
                Send Invitation
              </Button>
            </form>
          </Card>
        </div>
      </div>
    </div>
  );
}
