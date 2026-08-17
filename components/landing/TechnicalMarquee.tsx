"use client";

import React from "react";

export function TechnicalMarquee() {
  const row1Text = "ANTIGRAVITY FOR LATEX • UNLIMITED FAST COMPILATION • AGENTIC AI ASSISTANCE • ";
  const row2Text = "UNLIMITED CO-AUTHORS • NO OVERLEAF LIMITS • 100% FREE & OPEN SOURCE • ";

  return (
    <section className="bg-black py-8 border-b-2 border-white/20 overflow-hidden select-none">
      {/* Row 1: Orange text */}
      <div className="overflow-hidden whitespace-nowrap flex py-2 border-b border-white/10">
        <div className="animate-marquee font-archivo font-black uppercase text-2xl sm:text-4xl lg:text-6xl tracking-tight text-[#00CC68] shrink-0">
          <span>{row1Text.repeat(8)}</span>
        </div>
      </div>

      {/* Row 2: White text reverse */}
      <div className="overflow-hidden whitespace-nowrap flex py-2">
        <div className="animate-marquee-reverse font-archivo font-black uppercase text-2xl sm:text-4xl lg:text-6xl tracking-tight text-white shrink-0">
          <span>{row2Text.repeat(8)}</span>
        </div>
      </div>
    </section>
  );
}
