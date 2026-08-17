"use client";

import React from "react";

export function BrandMarquee() {
  const row1Text = "100% FREE • LIKE ANTIGRAVITY FOR LATEX • BLAZING FAST COMPILATION • ";
  const row2Text = "AGENTIC AI ASSISTANCE • FASTER THAN OVERLEAF • UNLIMITED CO-AUTHORS • ";

  return (
    <section className="bg-black py-8 border-b-2 border-black overflow-hidden select-none">
      {/* Row 1: Orange text moving left */}
      <div className="overflow-hidden whitespace-nowrap flex py-2 border-b border-white/10">
        <div className="animate-marquee font-archivo font-black uppercase text-3xl sm:text-5xl lg:text-7xl tracking-tighter text-[#00CC68] shrink-0">
          <span>{row1Text.repeat(8)}</span>
        </div>
      </div>

      {/* Row 2: White text moving right */}
      <div className="overflow-hidden whitespace-nowrap flex py-2">
        <div className="animate-marquee-reverse font-archivo font-black uppercase text-3xl sm:text-5xl lg:text-7xl tracking-tighter text-white shrink-0">
          <span>{row2Text.repeat(8)}</span>
        </div>
      </div>
    </section>
  );
}
