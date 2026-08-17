"use client";

import React from "react";

export function LandingIntroduction() {
  const tags = [
    "AGENTIC LATEX",
    "FASTER THAN OVERLEAF",
    "UNLIMITED COMPILATION",
    "AGENTIC AI ASSISTANCE",
    "UNLIMITED CO-AUTHORS",
    "100% OPEN SOURCE",
  ];

  return (
    <section className="bg-black text-white py-24 px-4 sm:px-8 lg:px-16 border-b-2 border-white/20 relative">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Label */}
        <div className="font-mono text-xs sm:text-sm font-bold text-[#00CC68] tracking-widest uppercase">
          01 // WHAT IS OVERBRANCH?
        </div>

        {/* Large Headline */}
        <h2 className="font-archivo font-black uppercase text-4xl sm:text-6xl lg:text-8xl tracking-[-0.04em] leading-[0.88] text-white max-w-5xl">
          THE ANTIGRAVITY FOR LATEX.
        </h2>

        {/* Asymmetric Split Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 pt-4">
          <div className="lg:col-span-8">
            <p className="font-sans text-lg sm:text-2xl text-zinc-300 leading-relaxed max-w-3xl">
              OverBranch is a 100% free and open-source agentic LaTeX code editor — like Antigravity for LaTeX. Built for students and scientific authors, it delivers unlimited, lightning-fast compilation compared to Overleaf, agentic AI assistance to prepare LaTeX documents, and real-time collaboration with unlimited co-authors per project.
            </p>
          </div>

          <div className="lg:col-span-4 flex flex-col justify-end">
            <div className="p-6 bg-white/5 border-2 border-white/20 space-y-3">
              <div className="font-mono text-xs text-[#00CC68] uppercase font-bold tracking-widest">
                ZERO RESTRICTIONS
              </div>
              <div className="font-archivo text-xl font-bold uppercase text-white">
                UNLIMITED COMPILATION & CO-AUTHORS
              </div>
            </div>
          </div>
        </div>

        {/* Technical Tags */}
        <div className="pt-8 flex flex-wrap gap-3">
          {tags.map((tag) => (
            <span
              key={tag}
              className="bg-white/10 text-white font-mono text-xs sm:text-sm font-bold px-4 py-2 uppercase tracking-wider border border-white/30 hover:bg-[#00CC68] hover:text-black hover:border-[#00CC68] transition-colors duration-150"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
