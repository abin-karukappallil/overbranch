"use client";

import React from "react";

export function LandingFreeSection() {
  const declarations = [
    "UNLIMITED COMPILATION",
    "UNLIMITED CO-AUTHORS",
    "AGENTIC AI ASSISTANCE",
    "FASTER THAN OVERLEAF",
  ];

  return (
    <section className="bg-[#00CC68] text-black py-24 px-4 sm:px-8 lg:px-16 border-b-2 border-black select-none">
      <div className="max-w-7xl mx-auto space-y-10">
        <span className="font-mono text-xs sm:text-sm font-bold tracking-widest uppercase block text-black">
          NO SUBSCRIPTION REQUIRED
        </span>

        <h2 className="font-archivo font-black uppercase text-5xl sm:text-7xl lg:text-[8vw] tracking-[-0.04em] leading-[0.85] text-black">
          100% FREE.
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-6">
          {declarations.map((item) => (
            <div
              key={item}
              className="bg-black text-white p-6 font-mono font-bold text-lg sm:text-xl uppercase tracking-wider border-2 border-black shadow-[5px_5px_0px_0px_#FFFFFF] flex items-center justify-center text-center"
            >
              {item}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
