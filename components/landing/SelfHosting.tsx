"use client";

import React, { useState } from "react";
import { Check, Copy, Terminal } from "lucide-react";

export function LandingSelfHosting() {
  const [copied, setCopied] = useState(false);

  const commandText = `$ git clone https://github.com/abin-karukappallil/overbranch.git\n$ cd overbranch \n //Add .env using .env.example \n$ docker compose up -d --build \n$ OverBranch Running\n  http://localhost:3000 // ONLINE`;

  const copyCommand = () => {
    navigator.clipboard.writeText("git clone https://github.com/abin-karukappallil/overbranch.git && cd overbranch && docker compose up -d");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const labels = ["UNLIMITED COMPILES", "UNLIMITED CO-AUTHORS", "AGENTIC AI", "YOUR INFRASTRUCTURE"];

  return (
    <section id="self-host" className="bg-[#00CC68] text-black py-24 px-4 sm:px-8 lg:px-16 border-b-2 border-black relative overflow-hidden select-none">
      <div className="max-w-7xl mx-auto space-y-12">
        {/* Header */}
        <div className="space-y-4 max-w-4xl">
          <span className="font-mono text-xs sm:text-sm font-bold tracking-widest text-black uppercase block">
            04 // YOUR INFRASTRUCTURE
          </span>
          <h2 className="font-archivo font-black uppercase text-5xl sm:text-7xl lg:text-9xl tracking-[-0.04em] leading-[0.88] text-black">
            RUN IT YOUR WAY.
          </h2>
          <p className="font-sans text-xl sm:text-2xl text-black font-semibold max-w-3xl leading-relaxed">
            Deploy your own high-performance LaTeX compilation server and agentic AI workspace. Enjoy zero compilation timeouts, zero file limits, and unlimited co-authors.
          </p>
        </div>

        {/* Technical Label Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {labels.map((lbl) => (
            <div
              key={lbl}
              className="bg-black text-white p-4 font-mono font-bold text-center text-sm sm:text-base tracking-wider uppercase border-2 border-black shadow-[4px_4px_0px_0px_#FFFFFF]"
            >
              {lbl}
            </div>
          ))}
        </div>

        {/* Brutalist Terminal Box */}
        <div className="bg-black text-white border-4 border-black p-6 sm:p-8 shadow-[8px_8px_0px_0px_#000000] relative">
          <div className="flex items-center justify-between pb-4 mb-6 border-b-2 border-white/20 font-mono text-xs text-[#00CC68] uppercase font-bold">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4" />
              <span>TERMINAL // DEPLOYMENT</span>
            </div>
            <button
              onClick={copyCommand}
              className="flex items-center gap-1.5 bg-white/10 hover:bg-[#00CC68] hover:text-black px-3 py-1 text-xs font-bold uppercase transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>COPIED</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>COPY COMMAND</span>
                </>
              )}
            </button>
          </div>

          <pre className="font-mono text-sm sm:text-lg lg:text-xl text-green-400 font-bold leading-relaxed overflow-x-auto">
            <code>{commandText}</code>
          </pre>
        </div>
      </div>
    </section>
  );
}
