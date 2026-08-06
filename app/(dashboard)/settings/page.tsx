"use client";

import React, { useState } from "react";
import {
  Settings,
  Palette,
  Shield,
  Key,
  Users,
  Save,
  Trash2,
  Plus,
  Copy,
  Check,
  Globe,
  Sun,
  Moon,
  Laptop,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { AnimatedTabs } from "@/components/ui/tabs-animated";
import { useTheme } from "next-themes";
import { toast } from "sonner";

const settingTabs = [
  { id: "general", label: "General", icon: Settings },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "auth", label: "Authentication", icon: Shield },
  { id: "apikeys", label: "API Keys", icon: Key },
  { id: "members", label: "Team Members", icon: Users },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("general");
  const { theme, setTheme } = useTheme();

  const [workspaceName, setWorkspaceName] = useState("Acme OverBranch");
  const [workspaceSlug, setWorkspaceSlug] = useState("acme-overbranch");
  const [copiedKey, setCopiedKey] = useState(false);

  const handleSaveGeneral = (e: React.FormEvent) => {
    e.preventDefault();
    toast.success("Workspace settings updated successfully");
  };

  const copyApiKey = () => {
    setCopiedKey(true);
    toast.success("API Key copied to clipboard");
    setTimeout(() => setCopiedKey(false), 2000);
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
          Workspace Settings
        </h1>
        <p className="text-sm text-muted-foreground">
          Manage workspace configuration, team members, themes, and API tokens.
        </p>
      </div>

      <AnimatedTabs tabs={settingTabs} activeTab={activeTab} onChange={setActiveTab} />

      {activeTab === "general" && (
        <Card className="p-6 sm:p-8 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl max-w-2xl space-y-6">
          <form onSubmit={handleSaveGeneral} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="ws-name">Workspace Name</Label>
              <Input
                id="ws-name"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
                className="h-11"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="ws-slug">Workspace Slug</Label>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-muted-foreground bg-muted px-3 py-2.5 rounded-lg border border-border/40">
                  overbranch.dev/
                </span>
                <Input
                  id="ws-slug"
                  value={workspaceSlug}
                  onChange={(e) => setWorkspaceSlug(e.target.value)}
                  className="h-11 font-mono"
                />
              </div>
            </div>

            <div className="pt-4 border-t border-border/40 flex justify-end">
              <Button type="submit" className="bg-indigo-600 text-white rounded-xl">
                <Save className="w-4 h-4 mr-2" />
                Save Changes
              </Button>
            </div>
          </form>
        </Card>
      )}

      {activeTab === "appearance" && (
        <Card className="p-6 sm:p-8 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl max-w-2xl space-y-6">
          <div>
            <h3 className="text-lg font-bold text-foreground">Theme Preference</h3>
            <p className="text-xs text-muted-foreground">Select your interface appearance theme</p>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <button
              onClick={() => setTheme("dark")}
              className={`p-5 rounded-2xl border flex flex-col items-center gap-3 transition-all ${
                theme === "dark" ? "border-indigo-500 bg-indigo-500/10 font-bold" : "border-border/60 hover:bg-accent"
              }`}
            >
              <Moon className="w-6 h-6 text-indigo-400" />
              <span className="text-xs">Dark Mode</span>
            </button>

            <button
              onClick={() => setTheme("light")}
              className={`p-5 rounded-2xl border flex flex-col items-center gap-3 transition-all ${
                theme === "light" ? "border-indigo-500 bg-indigo-500/10 font-bold" : "border-border/60 hover:bg-accent"
              }`}
            >
              <Sun className="w-6 h-6 text-amber-500" />
              <span className="text-xs">Light Mode</span>
            </button>

            <button
              onClick={() => setTheme("system")}
              className={`p-5 rounded-2xl border flex flex-col items-center gap-3 transition-all ${
                theme === "system" ? "border-indigo-500 bg-indigo-500/10 font-bold" : "border-border/60 hover:bg-accent"
              }`}
            >
              <Laptop className="w-6 h-6 text-slate-400" />
              <span className="text-xs">System</span>
            </button>
          </div>
        </Card>
      )}

      {activeTab === "auth" && (
        <Card className="p-6 sm:p-8 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl max-w-2xl space-y-6">
          <div>
            <h3 className="text-lg font-bold text-foreground">Better Auth Configuration</h3>
            <p className="text-xs text-muted-foreground">Session duration and OAuth bindings</p>
          </div>

          <div className="space-y-4 text-xs font-mono">
            <div className="p-4 rounded-xl border border-border/40 bg-muted/30 flex items-center justify-between">
              <div>
                <span className="font-bold text-foreground block">Google OAuth Status</span>
                <span className="text-emerald-400">Enabled & Configured</span>
              </div>
              <Button variant="outline" size="sm">Configure</Button>
            </div>

            <div className="p-4 rounded-xl border border-border/40 bg-muted/30 flex items-center justify-between">
              <div>
                <span className="font-bold text-foreground block">Session Duration</span>
                <span className="text-muted-foreground">30 Days Persistent Token</span>
              </div>
              <Button variant="outline" size="sm">Edit</Button>
            </div>
          </div>
        </Card>
      )}

      {activeTab === "apikeys" && (
        <Card className="p-6 sm:p-8 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl max-w-2xl space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-foreground">API Keys & Tokens</h3>
              <p className="text-xs text-muted-foreground">For CI/CD and Supabase Drizzle migrations</p>
            </div>
            <Button size="sm" onClick={() => toast.info("New API Key Generated")} className="bg-indigo-600 text-white">
              <Plus className="w-4 h-4 mr-1.5" />
              Create Token
            </Button>
          </div>

          <div className="p-4 rounded-xl border border-border/40 bg-muted/20 flex items-center justify-between text-xs font-mono">
            <div className="space-y-1">
              <span className="text-foreground font-bold block">ob_live_pk_994827103847</span>
              <span className="text-muted-foreground text-[10px]">Created Aug 2026 — Never Expires</span>
            </div>
            <Button variant="ghost" size="icon" onClick={copyApiKey}>
              {copiedKey ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            </Button>
          </div>
        </Card>
      )}

      {activeTab === "members" && (
        <Card className="p-6 sm:p-8 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl max-w-2xl space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-foreground">Workspace Members</h3>
              <p className="text-xs text-muted-foreground">Team access roles and permissions</p>
            </div>
            <Button size="sm" onClick={() => toast.info("Invite Member Dialog")} className="bg-indigo-600 text-white">
              <Plus className="w-4 h-4 mr-1.5" />
              Invite Member
            </Button>
          </div>

          <div className="space-y-3">
            <div className="p-3 rounded-xl border border-border/40 bg-muted/20 flex items-center justify-between text-xs">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center text-white font-bold">
                  AR
                </div>
                <div>
                  <span className="font-bold text-foreground block">Alex Rivers (You)</span>
                  <span className="text-muted-foreground font-mono">alex@overbranch.dev</span>
                </div>
              </div>
              <span className="px-2.5 py-1 rounded-full bg-indigo-500/10 text-indigo-400 font-mono font-bold">
                Owner
              </span>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
