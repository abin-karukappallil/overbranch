"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight, LayoutDashboard } from "lucide-react";
import { authClient } from "@/lib/auth-client";

export function LandingCTA() {
  const { data: session } = authClient.useSession();
  const isAuthenticated = Boolean(session?.user);

  return (
    <section className="bg-[#00CC68] text-black py-28 px-4 sm:px-8 lg:px-16 text-center border-b-2 border-black relative overflow-hidden select-none">
      <div className="max-w-5xl mx-auto space-y-8">
        <span className="font-mono text-xs sm:text-base font-bold tracking-widest uppercase block text-black">
          READY TO BUILD DIFFERENTLY?
        </span>

        <h2 className="font-archivo font-black uppercase text-6xl sm:text-8xl lg:text-9xl tracking-[-0.04em] leading-[0.88] text-black">
          FORK THE FUTURE.
        </h2>

        <p className="font-sans text-xl sm:text-3xl text-black font-semibold max-w-2xl mx-auto leading-relaxed">
          Start writing LaTeX with agentic AI, instant compilation, and unlimited co-authors. Self-host it. Change anything.
        </p>

        <div className="pt-6 flex justify-center">
          {isAuthenticated ? (
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-3 bg-black text-white font-mono text-lg sm:text-2xl font-bold uppercase tracking-wider px-10 py-5 rounded-full border-2 border-black shadow-[6px_6px_0px_0px_#FFFFFF] hover:scale-110 hover:translate-x-2 transition-all duration-200"
            >
              <LayoutDashboard className="w-6 h-6 text-[#00CC68]" />
              <span>GO TO WORKSPACE</span>
              <ArrowRight className="w-6 h-6 stroke-[3]" />
            </Link>
          ) : (
            <Link
              href="/register"
              className="inline-flex items-center gap-3 bg-black text-white font-mono text-lg sm:text-2xl font-bold uppercase tracking-wider px-10 py-5 rounded-full border-2 border-black shadow-[6px_6px_0px_0px_#FFFFFF] hover:scale-110 hover:translate-x-2 transition-all duration-200"
            >
              <span className="flex items-center gap-2">
                <span>GET OVERBRANCH</span>
                <span className="text-[10px] sm:text-xs px-2 py-0.5 rounded bg-[#00CC68] text-black font-black uppercase tracking-wider">
                  BETA
                </span>
              </span>
              <ArrowRight className="w-6 h-6 stroke-[3] text-[#00CC68]" />
            </Link>
          )}
        </div>

     
       

        <div className="font-mono text-xs sm:text-sm font-bold tracking-widest text-black/90 pt-6 uppercase">
          ANTIGRAVITY FOR LATEX · FASTER THAN OVERLEAF · UNLIMITED CO-AUTHORS
        </div>
      </div>
    </section>
  );
}
