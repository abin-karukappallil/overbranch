"use client";

import React, { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import gsap from "gsap";
import {
  Zap,
  ShieldCheck,
  Smartphone,
  Layers,
  Sparkles,
  GitPullRequest,
  Database,
  Lock,
  Palette,
  Terminal,
} from "lucide-react";
import { Card } from "@/components/ui/card";

const featureList = [
  {
    icon: Zap,
    title: "Instant Environment Fluidity",
    description: "Zero boot delay. Workspaces load instantly with pre-cached assets and unified state management.",
    gradient: "from-indigo-500/10 via-purple-500/10 to-transparent",
    borderGlow: "group-hover:border-indigo-500/40",
    iconColor: "text-indigo-400",
  },
  {
    icon: ShieldCheck,
    title: "Better Auth & Supabase Core",
    description: "Production-grade authentication with Google OAuth, session management, and Drizzle ORM PostgreSQL integration.",
    gradient: "from-cyan-500/10 via-blue-500/10 to-transparent",
    borderGlow: "group-hover:border-cyan-500/40",
    iconColor: "text-cyan-400",
  },
  {
    icon: Smartphone,
    title: "Strict Universal Responsiveness",
    description: "Tailored experience from ultra-wide 4K monitors down to foldable devices and small smartphone displays.",
    gradient: "from-emerald-500/10 via-teal-500/10 to-transparent",
    borderGlow: "group-hover:border-emerald-500/40",
    iconColor: "text-emerald-400",
  },
  {
    icon: Palette,
    title: "Linear & Raycast Aesthetic",
    description: "Curated dark mode standard with glassmorphic layers, soft glowing indicators, and smooth micro-animations.",
    gradient: "from-purple-500/10 via-pink-500/10 to-transparent",
    borderGlow: "group-hover:border-purple-500/40",
    iconColor: "text-purple-400",
  },
  {
    icon: GitPullRequest,
    title: "Seamless Branch Tracking",
    description: "Instant visual diffs, branch tracking, and commit timeline overview without leaves-the-editor context switches.",
    gradient: "from-amber-500/10 via-orange-500/10 to-transparent",
    borderGlow: "group-hover:border-amber-500/40",
    iconColor: "text-amber-400",
  },
  {
    icon: Terminal,
    title: "Keyboard-First Command Matrix",
    description: "Global Cmd+K command palette for instant search, workspace switching, dark/light themes, and quick actions.",
    gradient: "from-rose-500/10 via-red-500/10 to-transparent",
    borderGlow: "group-hover:border-rose-500/40",
    iconColor: "text-rose-400",
  },
];

export function LandingFeatures() {
  const sectionRef = useRef<HTMLDivElement>(null);

  return (
    <section id="features" ref={sectionRef} className="py-24 px-4 sm:px-6 lg:px-8 relative border-t border-border/40">
      <div className="max-w-7xl mx-auto space-y-16">
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-indigo-500/20 bg-indigo-500/10 text-xs font-semibold text-indigo-400 uppercase tracking-widest">
            <Sparkles className="w-3.5 h-3.5" />
            Designed For Modern Engineers
          </div>
          <h2 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-foreground">
            Crafted for speed, precision, and elegance
          </h2>
          <p className="text-base sm:text-lg text-muted-foreground leading-relaxed">
            Every surface of OverBranch is tuned for maximum clarity and ergonomic comfort during long coding sessions.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {featureList.map((feature, idx) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: idx * 0.1 }}
            >
              <Card
                className={`group relative p-8 h-full rounded-2xl border border-border/60 bg-card/40 backdrop-blur-xl hover:shadow-2xl transition-all duration-300 ${feature.borderGlow} overflow-hidden`}
              >
                <div
                  className={`absolute inset-0 bg-gradient-to-br ${feature.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-500`}
                />

                <div className="relative z-10 space-y-4">
                  <div className="w-12 h-12 rounded-xl bg-muted/80 border border-border/40 flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
                    <feature.icon className={`w-6 h-6 ${feature.iconColor}`} />
                  </div>
                  <h3 className="text-xl font-bold tracking-tight text-foreground">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {feature.description}
                  </p>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
