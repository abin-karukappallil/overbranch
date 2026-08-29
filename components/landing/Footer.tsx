"use client";

import React from "react";

export function LandingFooter() {
  return (
    <footer className="bg-[#00CC68] text-black border-t-2 border-black py-16 px-4 sm:px-8 lg:px-16 font-mono text-xs sm:text-sm font-bold uppercase tracking-wider select-none">
      <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-12 items-start">
        {/* Left Column */}
        <div className="space-y-2 text-center md:text-left">
          <div className="font-archivo text-2xl font-black tracking-tight text-black">
            OVERBRANCH
          </div>
          <div className="text-black/80">© 2026 OVERBRANCH</div>
          <div className="text-black/80">OPEN SOURCE SOFTWARE</div>
        </div>

        {/* Center Column */}
        <div className="space-y-2 text-center">
          <div>
            <a href="#pdf-to-latex" className="text-black hover:bg-black hover:text-white px-2 py-1 transition-colors">
              PDF TO LATEX
            </a>
          </div>
          <div>
            <a href="#templates" className="text-black hover:bg-black hover:text-white px-2 py-1 transition-colors">
              TEMPLATES
            </a>
          </div>
          <div className="text-black/80">100% FREE & SELF-HOSTABLE</div>
        </div>

        {/* Right Column */}
        <div className="space-y-2 text-center md:text-right">
          <div>
            <a
              href="https://github.com/abin-karukappallil/overbranch"
              target="_blank"
              rel="noopener noreferrer"
              className="text-black hover:bg-black hover:text-white px-2 py-1 transition-colors"
            >
              GITHUB
            </a>
          </div>
          <div>
            <a
              href="#self-host"
              className="text-black hover:bg-black hover:text-white px-2 py-1 transition-colors"
            >
              DOCS
            </a>
          </div>
          <div>
            <a
              href="https://github.com/abin-karukappallil/overbranch"
              target="_blank"
              rel="noopener noreferrer"
              className="text-black hover:bg-black hover:text-white px-2 py-1 transition-colors"
            >
              COMMUNITY
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
