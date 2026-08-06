"use client";

import React from "react";
import { Check, Shield, Sparkles, CreditCard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";

export default function BillingPage() {
  return (
    <div className="space-y-8 animate-fade-in pb-12 max-w-4xl">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
          Billing & Subscription Plans
        </h1>
        <p className="text-sm text-muted-foreground">
          Manage team seat licenses, pdfLaTeX compilation quotas, and enterprise support.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-6 rounded-2xl border border-indigo-500/40 bg-indigo-500/10 backdrop-blur-xl space-y-4 relative">
          <div className="px-3 py-1 rounded-full bg-indigo-500 text-white font-mono text-[10px] uppercase font-bold w-fit">
            Current Active Plan
          </div>
          <h2 className="text-2xl font-bold text-foreground">Pro Researcher Team</h2>
          <p className="text-xs text-muted-foreground">Unlimited pdfLaTeX compilations & real-time co-authoring.</p>
          <div className="text-3xl font-extrabold text-foreground font-mono">
            $29 <span className="text-xs text-muted-foreground font-normal">/ member / month</span>
          </div>

          <div className="space-y-2 text-xs text-muted-foreground pt-2">
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>Unlimited LaTeX PDF compilations</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>Up to 25 active co-authors per workspace</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>BibTeX DOI auto-sync & Zotero integration</span>
            </div>
          </div>

          <Button onClick={() => toast.info("Managing subscription details")} className="w-full bg-indigo-600 text-white rounded-xl">
            Manage Subscription
          </Button>
        </Card>

        <Card className="p-6 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl space-y-4">
          <h2 className="text-2xl font-bold text-foreground">Enterprise Custom</h2>
          <p className="text-xs text-muted-foreground">Self-hosted Supabase + custom TeX compilation server clusters.</p>
          <div className="text-3xl font-extrabold text-foreground font-mono">
            Custom
          </div>

          <div className="space-y-2 text-xs text-muted-foreground pt-2">
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-indigo-400" />
              <span>Dedicated XeLaTeX / LuaLaTeX rendering cluster</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-indigo-400" />
              <span>SAML SSO & custom Better Auth provider integration</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-indigo-400" />
              <span>24/7 Priority SLA support</span>
            </div>
          </div>

          <Button variant="outline" onClick={() => toast.info("Contacting Enterprise Sales")} className="w-full rounded-xl">
            Contact Sales
          </Button>
        </Card>
      </div>
    </div>
  );
}
