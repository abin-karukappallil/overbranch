"use client";

import React from "react";
import Link from "next/link";
import { Star, ArrowUpRight, ArrowRight, LayoutDashboard } from "lucide-react";
import { authClient } from "@/lib/auth-client";

export function LandingHero() {
  const { data: session } = authClient.useSession();
  const isAuthenticated = Boolean(session?.user);

  return (
    <section id="product" className="relative min-h-screen bg-[#00CC68] text-black flex flex-col justify-between pt-28 pb-10 px-4 sm:px-8 lg:px-12 select-none border-b-2 border-black overflow-hidden">
      {/* Top / Main Hero Content */}
      <div className="relative z-10 flex-1 flex flex-col justify-center items-center text-center my-auto">
    

        <h1 className="font-archivo font-black uppercase text-4xl sm:text-6xl md:text-7xl lg:text-8xl xl:text-[8vw] tracking-[-0.04em] leading-[0.9] text-black max-w-full drop-shadow-sm flex items-center justify-center gap-3 flex-wrap">
          <span>OVERBRANCH</span>
          <span className="text-xs sm:text-base md:text-xl font-mono font-black uppercase bg-black text-[#00CC68] px-2.5 py-1 rounded-md tracking-widest self-center shadow-[3px_3px_0px_0px_#000000]">
            BETA
          </span>
        </h1>

        <h2 className="font-archivo font-black uppercase text-lg sm:text-3xl lg:text-4xl tracking-[-0.03em] leading-[1.05] text-black max-w-4xl mt-4 px-2">
          AGENTIC LATEX CODE EDITOR FOR STUDENTS AND RESEARCHERS
        </h2>

        <p className="font-mono text-xs sm:text-base lg:text-lg font-bold uppercase tracking-tight text-black max-w-4xl mt-4 px-2 leading-relaxed">
          LIKE ANTIGRAVITY FOR LATEX • UNLIMITED FAST COMPILATION VS OVERLEAF • AGENTIC AI & UNLIMITED CO-AUTHORS
        </p>

     

        {/* Hero CTA Action Button Pair */}
        <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
          {isAuthenticated ? (
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-3 bg-black text-white px-7 py-4 rounded-full font-mono text-sm sm:text-base font-bold uppercase tracking-wider border-2 border-black hover:bg-white hover:text-black shadow-[5px_5px_0px_0px_#000000] hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none transition-all duration-150"
            >
              <LayoutDashboard className="w-5 h-5 text-[#00CC68]" />
              <span>GO TO WORKSPACE</span>
              <ArrowRight className="w-4 h-4 text-[#00CC68]" />
            </Link>
          ) : (
            <Link
              href="/register"
              className="inline-flex items-center gap-3 bg-black text-white px-7 py-4 rounded-full font-mono text-sm sm:text-base font-bold uppercase tracking-wider border-2 border-black hover:bg-white hover:text-black shadow-[5px_5px_0px_0px_#000000] hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none transition-all duration-150"
            >
              <span>GET STARTED FREE</span>
              <ArrowRight className="w-4 h-4 text-[#00CC68]" />
            </Link>
          )}

          <a
            href="https://github.com/abin-karukappallil/overbranch"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-3 bg-white text-black px-7 py-4 rounded-full font-mono text-sm sm:text-base font-bold uppercase tracking-wider border-2 border-black hover:bg-black hover:text-white shadow-[5px_5px_0px_0px_#000000] hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none transition-all duration-150"
          >
            <Star className="w-5 h-5 text-[#00CC68] fill-[#00CC68]" />
            <span>STAR ON GITHUB</span>
            <ArrowUpRight className="w-4 h-4" />
          </a>
        </div>
      </div>

      {/* Hero Footer Area with 2px Black Divider */}
      <div className="w-full mt-10">
        <div className="w-full border-b-2 border-black mb-6" />

        <div className="flex flex-col md:flex-row items-center justify-between gap-6 font-mono text-xs sm:text-sm font-bold uppercase tracking-wider">
          {/* Left Metadata */}
          <div className="text-center md:text-left">
            <span className="text-2xl sm:text-4xl font-archivo font-black tracking-tighter block text-black">
              Fully Free and Fast
            </span>
          </div>

          {/* Right Metadata */}
          <div className="text-center md:text-right space-y-1 text-black/90">
            <div>FASTER THAN OVERLEAF</div>
            <div>UNLIMITED CO-AUTHORS</div>
            <div>AGENTIC AI ASSISTANT</div>
          </div>
        </div>
      </div>
    </section>
  );
}
