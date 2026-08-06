"use client";

import React, { useState } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Users, UserPlus, Share2, Sparkles, X, Check } from "lucide-react";
import { toast } from "sonner";

interface Collaborator {
  id: string;
  name: string;
  avatar: string;
  color: string;
  status: "active" | "idle";
  cursorFile: string;
}

const mockCollaborators: Collaborator[] = [
  {
    id: "1",
    name: "Dr. Alice Vance",
    avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80",
    color: "#818cf8",
    status: "active",
    cursorFile: "main.tex (Ln 14)",
  },
  {
    id: "2",
    name: "Prof. Bob Chen",
    avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80",
    color: "#38bdf8",
    status: "active",
    cursorFile: "references.bib (Ln 28)",
  },
  {
    id: "3",
    name: "Carol Zhang",
    avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80",
    color: "#34d399",
    status: "idle",
    cursorFile: "sections/abstract.tex",
  },
];

export function CollaboratorAvatars() {
  const [mobileModalOpen, setMobileModalOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleShare = () => {
    setCopied(true);
    toast.success("Collaborative LaTeX Session link copied!", {
      description: "Mobile co-authors can join and edit in real time.",
    });
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-2">
      <div
        onClick={() => setMobileModalOpen(true)}
        className="flex items-center -space-x-2 overflow-hidden cursor-pointer"
        title="View Active Collaborators"
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
              <p className="font-bold text-foreground">{c.name}</p>
              <p className="text-[10px] text-muted-foreground font-mono">Editing: {c.cursorFile}</p>
            </div>
          </div>
        ))}
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={handleShare}
        className="h-8 px-2.5 border-border/60 bg-card/60 backdrop-blur-md text-xs font-medium"
      >
        {copied ? (
          <Check className="w-3.5 h-3.5 text-emerald-400" />
        ) : (
          <Share2 className="w-3.5 h-3.5 text-indigo-400 sm:mr-1.5" />
        )}
        <span className="hidden sm:inline">{copied ? "Copied" : "Share"}</span>
      </Button>

      {mobileModalOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-background/80 backdrop-blur-md">
          <div className="w-full max-w-md p-6 rounded-t-3xl sm:rounded-2xl border border-border/80 bg-card shadow-2xl space-y-4 animate-slide-up">
            <div className="flex items-center justify-between border-b border-border/40 pb-3">
              <div className="flex items-center gap-2">
                <Users className="w-5 h-5 text-indigo-400" />
                <h3 className="font-bold text-base text-foreground">Active Co-Authors</h3>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setMobileModalOpen(false)} className="h-8 w-8">
                <X className="w-4 h-4" />
              </Button>
            </div>

            <div className="space-y-3 max-h-60 overflow-y-auto">
              {mockCollaborators.map((c) => (
                <div key={c.id} className="p-3 rounded-xl border border-border/40 bg-muted/20 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <Avatar className="w-9 h-9 rounded-full">
                      <AvatarImage src={c.avatar} />
                      <AvatarFallback>{c.name.slice(0, 2)}</AvatarFallback>
                    </Avatar>
                    <div>
                      <p className="font-bold text-foreground">{c.name}</p>
                      <p className="text-[10px] text-muted-foreground font-mono">Editing: {c.cursorFile}</p>
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

            <Button onClick={handleShare} className="w-full bg-indigo-600 text-white rounded-xl">
              <Share2 className="w-4 h-4 mr-2" />
              Copy Collaboration Invite Link
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
