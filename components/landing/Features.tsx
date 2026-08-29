"use client";

import React from "react";
import { ArrowRight } from "lucide-react";

interface FeatureRow {
  index: string;
  title: string;
  tags: string[];
}

const features: FeatureRow[] = [
  {
    index: "01",
    title: "AGENTIC AI FOR LATEX",
    tags: ["AGENTIC ASSISTANT", "DOCUMENT DRAFTING", "AUTO-FIX ERRORS", "ANTIGRAVITY IDE"],
  },
  {
    index: "02",
    title: "AI PDF TO LATEX CONVERTER",
    tags: ["STATIC PDF TO CODE", "EQUATION OCR", "EMBEDDED FIGURES", "AUTO-STRUCTURE"],
  },
  {
    index: "03",
    title: "CURATED TEMPLATE VAULT",
    tags: ["BEAMER DECKS", "IEEE & ACM PAPERS", "DEVELOPER CVS", "PHD THESES"],
  },
  {
    index: "04",
    title: "BLAZING FAST COMPILATION",
    tags: ["UNLIMITED COMPILES", "FASTER THAN OVERLEAF", "INSTANT PDF", "ZERO TIMEOUTS"],
  },
  {
    index: "05",
    title: "UNLIMITED COLLABORATION",
    tags: ["UNLIMITED CO-AUTHORS", "REALTIME CO-AUTHORING", "NO TEAM LIMITS", "PROJECT SHARING"],
  },
  {
    index: "06",
    title: "100% FREE & OPEN SOURCE",
    tags: ["NO SUBSCRIPTIONS", "SELF-HOSTABLE", "TRANSPARENT CODE", "NO PAYWALLS"],
  },
  {
    index: "07",
    title: "RESEARCHER & STUDENT FIRST",
    tags: ["PRIVATE DATA", "LOCAL MODELS", "GIT COLLABORATION", "YOUR SERVER"],
  },
];

export function LandingFeatures() {
  return (
    <section id="features" className="bg-black text-white py-24 border-b-2 border-white/20 select-none">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 mb-12">
        <div className="font-mono text-xs sm:text-sm font-bold text-[#00CC68] tracking-widest uppercase mb-2">
          SYSTEM CORE FEATURES
        </div>
        <h2 className="font-archivo font-black uppercase text-3xl sm:text-5xl text-white tracking-tight">
          BUILT FOR ABSOLUTE CONTROL.
        </h2>
      </div>

      {/* Feature Service List Rows */}
      <div className="divide-y-2 divide-white/10 border-y-2 border-white/10">
        {features.map((feature) => (
          <div
            key={feature.index}
            className="group px-4 sm:px-8 lg:px-16 py-8 hover:bg-white/5 transition-colors duration-150 ease-out cursor-pointer"
          >
            <div className="max-w-7xl mx-auto flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
              {/* Index & Title */}
              <div className="flex items-center gap-6 group-hover:translate-x-4 transition-transform duration-150 ease-out">
                <span className="font-mono text-base sm:text-xl font-bold text-[#00CC68]">
                  {feature.index}
                </span>
                <h3 className="font-archivo font-black uppercase text-2xl sm:text-4xl lg:text-5xl text-white tracking-[-0.03em]">
                  {feature.title}
                </h3>
              </div>

              {/* Tags & Arrow */}
              <div className="flex items-center justify-between w-full lg:w-auto gap-6 pt-2 lg:pt-0">
                <div className="flex flex-wrap gap-2">
                  {feature.tags.map((tag) => (
                    <span
                      key={tag}
                      className="font-mono text-[10px] sm:text-xs font-bold uppercase tracking-wider bg-white/10 px-2.5 py-1 text-zinc-300 group-hover:text-white group-hover:bg-white/20 transition-colors"
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                <div className="text-[#00CC68] group-hover:rotate-45 transition-transform duration-150 ease-out shrink-0">
                  <ArrowRight className="w-8 h-8 sm:w-10 sm:h-10 stroke-[2.5]" />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
