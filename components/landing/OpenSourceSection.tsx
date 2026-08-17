"use client";

import React from "react";
import { ArrowUpRight } from "lucide-react";

export function LandingOpenSource() {
  return (
    <section className="bg-black text-white py-24 px-4 sm:px-8 lg:px-16 border-b-2 border-white/20 select-none">
      <div className="max-w-7xl mx-auto space-y-8">
        <div className="font-mono text-xs sm:text-sm font-bold text-[#00CC68] tracking-widest uppercase">
          03 // FULL TRANSPARENCY
        </div>

        <h2 className="font-archivo font-black uppercase text-5xl sm:text-7xl lg:text-9xl tracking-[-0.04em] leading-[0.88] text-[#00CC68] max-w-5xl">
          THE CODE IS YOURS.
        </h2>

        <p className="font-sans text-xl sm:text-3xl text-zinc-200 max-w-3xl leading-relaxed">
          OverBranch is 100% free and open source. The agentic LaTeX editor for researchers who demand lightning-fast compilation, AI document drafting, and unlimited co-authors with zero paywalls.
        </p>

        <div className="pt-6">
          <a
            href="https://github.com/abin-karukappallil/overbranch"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-3 bg-[#00CC68] text-black font-mono text-lg sm:text-2xl font-bold uppercase tracking-wider px-8 py-5 rounded-full border-2 border-black shadow-[6px_6px_0px_0px_#FFFFFF] hover:bg-white hover:text-black hover:translate-x-1 hover:translate-y-1 transition-all duration-150"
          >
            <span>VIEW SOURCE</span>
            <ArrowUpRight className="w-7 h-7 stroke-[3]" />
          </a>
        </div>
      </div>
    </section>
  );
}
