"use client";

import React, { useState } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Users, UserPlus, Share2, Sparkles, X, Check, Mail, Shield } from "lucide-react";
import { toast } from "sonner";

interface Collaborator {
  id: string;
  name: string;
  avatar: string;
  color: string;
  status: "active" | "idle";
  cursorFile: string;
  role: string;
}

const mockCollaborators: Collaborator[] = [
  {
    id: "1",
    name: "Dr. Alice Vance",
    avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80",
    color: "#818cf8",
    status: "active",
    cursorFile: "main.tex (Ln 14)",
    role: "Owner",
  },
  {
    id: "2",
    name: "Prof. Bob Chen",
    avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80",
    color: "#38bdf8",
    status: "active",
    cursorFile: "references.bib (Ln 28)",
    role: "Editor",
  },
  {
    id: "3",
    name: "Carol Zhang",
    avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80",
    color: "#34d399",
    status: "idle",
    cursorFile: "sections/abstract.tex",
    role: "Viewer",
  },
];

export function CollaboratorAvatars() {
  const [mobileModalOpen, setMobileModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("Editor");
  const [copied, setCopied] = useState(false);

  const handleShare = () => {
    setCopied(true);
    toast.success("Direct Project Invite Link copied to clipboard!", {
      description: "Co-authors can join and edit this LaTeX manuscript in real time.",
    });
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSendInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail) return;
    toast.success(`Project co-author invitation sent to ${inviteEmail} (${inviteRole})`);
    setInviteEmail("");
  };

  return (
    <div className="flex items-center gap-2">
      <div
        onClick={() => setMobileModalOpen(true)}
        className="flex items-center -space-x-2 overflow-hidden cursor-pointer"
        title="Manage Project Co-Authors"
      >
        {mockCollaborators.map((c) => (
          <div key={c.id} className="relative group">
            <Avatar className="w-7 h-7 sm:w-8 sm:h-8 rounded-full border-2 border-background shadow-md">
              <AvatarImage src={c.avatar} alt={c.name} />
              <AvatarFallback style={{ backgroundColor: c.color }} className="text-white text-xs font-bold">
                {c.name.slice(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            {c.status === "active" && (
              <span
                className="absolute bottom-0 right-0 w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full border border-background"
                style={{ backgroundColor: c.color }}
              />
            )}

            <div className="absolute right-0 top-10 hidden group-hover:block z-50 p-2.5 rounded-xl border border-border/60 bg-card/95 backdrop-blur-xl shadow-2xl text-xs whitespace-nowrap space-y-1">
              <p className="font-bold text-foreground">{c.name} ({c.role})</p>
              <p className="text-[10px] text-muted-foreground font-mono">Editing: {c.cursorFile}</p>
            </div>
          </div>
        ))}
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={() => setMobileModalOpen(true)}
        className="h-8 px-2.5 border-border/60 bg-card/60 backdrop-blur-md text-xs font-medium"
      >
        <UserPlus className="w-3.5 h-3.5 text-indigo-400 sm:mr-1.5" />
        <span className="hidden sm:inline">Invite Co-Author</span>
      </Button>

      {mobileModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md">
          <div className="w-full max-w-md p-6 rounded-2xl border border-border/80 bg-card shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-border/40 pb-3">
              <div className="flex items-center gap-2">
                <Users className="w-5 h-5 text-indigo-400" />
                <h3 className="font-bold text-base text-foreground">Project Co-Authors</h3>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setMobileModalOpen(false)} className="h-8 w-8">
                <X className="w-4 h-4" />
              </Button>
            </div>

            <form onSubmit={handleSendInvite} className="space-y-3">
              <span className="text-xs font-bold text-foreground block">Invite Co-Author to Project</span>
              <div className="flex gap-2">
                <Input
                  type="email"
                  placeholder="coauthor@university.edu"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  className="h-9 text-xs"
                />
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="h-9 px-2 text-xs rounded-lg border border-border/60 bg-background text-foreground outline-none font-mono"
                >
                  <option value="Editor">Editor</option>
                  <option value="Viewer">Viewer</option>
                </select>
              </div>
              <Button type="submit" className="w-full bg-indigo-600 text-white rounded-xl h-9 text-xs">
                Send Direct Invite
              </Button>
            </form>

            <div className="space-y-2 border-t border-border/40 pt-3">
              <span className="text-xs font-bold text-foreground block">Active Project Members ({mockCollaborators.length})</span>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {mockCollaborators.map((c) => (
                  <div key={c.id} className="p-2.5 rounded-xl border border-border/40 bg-muted/20 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2.5">
                      <Avatar className="w-7 h-7 rounded-full">
                        <AvatarImage src={c.avatar} />
                        <AvatarFallback>{c.name.slice(0, 2)}</AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-bold text-foreground text-[11px]">{c.name}</p>
                        <p className="text-[10px] text-muted-foreground font-mono">{c.role}</p>
                      </div>
                    </div>
                    <span
                      className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase"
                      style={{ color: c.color, backgroundColor: `${c.color}15` }}
                    >
                      {c.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <Button onClick={handleShare} variant="outline" className="w-full rounded-xl h-9 text-xs">
              <Share2 className="w-3.5 h-3.5 mr-2 text-indigo-400" />
              {copied ? "Invite Link Copied!" : "Copy Project Invite Link"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
