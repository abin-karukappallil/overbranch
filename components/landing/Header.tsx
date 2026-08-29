"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Menu, X, ArrowUpRight, LayoutDashboard, Star } from "lucide-react";
import { authClient } from "@/lib/auth-client";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

export function LandingHeader() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { data: session } = authClient.useSession();
  const isAuthenticated = Boolean(session?.user);

  return (
    <header className="fixed top-4 left-0 right-0 z-50 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto flex items-center justify-between gap-3 pointer-events-none">
      {/* Left Branding with Logo */}
      <Link
        href="/"
        className="pointer-events-auto shrink-0 flex items-center gap-2 font-archivo text-lg sm:text-xl font-black uppercase tracking-[-0.04em] text-black bg-[#00CC68] px-3 py-1.5 border-2 border-black shadow-[3px_3px_0px_0px_#000000] hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none transition-all duration-150"
      >
        <OverBranchLogo size="sm" variant="icon" colored={false} iconClassName="text-black stroke-black" />
        <span>OVERBRANCH</span>
      </Link>

      {/* Center Navigation Pill */}
      <nav className="pointer-events-auto hidden lg:flex items-center gap-1 bg-black text-white px-3 py-1.5 rounded-full border-2 border-black font-mono text-[11px] xl:text-xs font-bold uppercase tracking-wider shadow-2xl shrink-0">
        <a
          href="#pdf-to-latex"
          className="px-2.5 py-1 rounded-full text-white/90 hover:bg-[#00CC68] hover:text-black transition-all duration-150"
        >
          PDF TO LATEX
        </a>
        <a
          href="#templates"
          className="px-2.5 py-1 rounded-full text-white/90 hover:bg-[#00CC68] hover:text-black transition-all duration-150"
        >
          TEMPLATES
        </a>
        <a
          href="#features"
          className="px-2.5 py-1 rounded-full text-white/90 hover:bg-white hover:text-black transition-all duration-150"
        >
          FEATURES
        </a>
        <a
          href="#self-host"
          className="px-2.5 py-1 rounded-full text-white/90 hover:bg-white hover:text-black transition-all duration-150"
        >
          SELF-HOST
        </a>
        <a
          href="https://github.com/abin-karukappallil/overbranch"
          target="_blank"
          rel="noopener noreferrer"
          className="px-2.5 py-1 rounded-full text-[#00CC68] hover:bg-white hover:text-black transition-all duration-150 flex items-center gap-1 font-bold"
        >
          <Star className="w-3 h-3 fill-[#00CC68]" />
          <span>GITHUB</span>
        </a>
      </nav>

      {/* Right Controls / Auth */}
      <div className="pointer-events-auto hidden lg:flex items-center gap-2.5 shrink-0">
        <div className="bg-black text-[#00CC68] px-3 py-1.5 rounded-full border-2 border-black font-mono text-[11px] xl:text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#00CC68] animate-pulse" />
          <span>OPEN SOURCE</span>
        </div>

        {isAuthenticated ? (
          <Link
            href="/dashboard"
            className="bg-black text-white px-4 py-1.5 rounded-full font-mono text-[11px] xl:text-xs font-bold uppercase tracking-wider border-2 border-black hover:bg-white hover:text-black transition-all duration-150 flex items-center gap-1.5 shrink-0"
          >
            <LayoutDashboard className="w-3.5 h-3.5 text-[#00CC68]" />
            <span>WORKSPACE</span>
          </Link>
        ) : (
          <Link
            href="/login"
            className="bg-black text-white px-4 py-1.5 rounded-full font-mono text-[11px] xl:text-xs font-bold uppercase tracking-wider border-2 border-black hover:bg-white hover:text-black transition-all duration-150 shrink-0"
          >
            SIGN IN
          </Link>
        )}
      </div>

      {/* Mobile / Tablet Menu Button */}
      <button
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        className="pointer-events-auto lg:hidden bg-black text-white p-2.5 rounded-full border-2 border-black shrink-0"
        aria-label="Toggle navigation menu"
      >
        {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Mobile Dropdown Menu */}
      {mobileMenuOpen && (
        <div className="pointer-events-auto md:hidden fixed inset-x-4 top-20 bg-black text-white p-6 border-4 border-black rounded-3xl shadow-2xl font-mono text-sm font-bold uppercase tracking-wider space-y-4 z-50">
          <div className="flex flex-col space-y-3">
            <a
              href="#product"
              onClick={() => setMobileMenuOpen(false)}
              className="px-3 py-2 rounded-lg hover:bg-white/10 text-white"
            >
              PRODUCT
            </a>
            <a
              href="#pdf-to-latex"
              onClick={() => setMobileMenuOpen(false)}
              className="px-3 py-2 rounded-lg hover:bg-[#00CC68]/20 text-[#00CC68]"
            >
              PDF TO LATEX
            </a>
            <a
              href="#templates"
              onClick={() => setMobileMenuOpen(false)}
              className="px-3 py-2 rounded-lg hover:bg-[#00CC68]/20 text-[#00CC68]"
            >
              TEMPLATES
            </a>
            <a
              href="#features"
              onClick={() => setMobileMenuOpen(false)}
              className="px-3 py-2 rounded-lg hover:bg-white/10 text-white"
            >
              FEATURES
            </a>
            <Link
              href={isAuthenticated ? "/dashboard?openPdfModal=true" : "/convert"}
              onClick={() => setMobileMenuOpen(false)}
              className="px-3 py-2 rounded-lg bg-[#00CC68]/15 text-[#00CC68] hover:bg-[#00CC68]/25 font-bold"
            >
              {isAuthenticated ? "PDF TO LATEX" : "PDF TO LATEX (FREE GUEST)"}
            </Link>
            <a
              href="#self-host"
              onClick={() => setMobileMenuOpen(false)}
              className="px-3 py-2 rounded-lg hover:bg-white/10 text-white"
            >
              SELF-HOST
            </a>
            <a
              href="https://github.com/abin-karukappallil/overbranch"
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setMobileMenuOpen(false)}
              className="px-3 py-2 rounded-lg hover:bg-white/10 text-[#00CC68] flex items-center justify-between font-bold"
            >
              <div className="flex items-center gap-2">
                <Star className="w-4 h-4 fill-[#00CC68]" />
                <span>STAR ON GITHUB</span>
              </div>
              <ArrowUpRight className="w-4 h-4" />
            </a>
            <a
              href="#self-host"
              onClick={() => setMobileMenuOpen(false)}
              className="px-3 py-2 rounded-lg hover:bg-white/10 text-white"
            >
              DOCUMENTATION
            </a>
          </div>

          <div className="pt-4 border-t-2 border-white/20 flex flex-col gap-3">
            {isAuthenticated ? (
              <Link
                href="/dashboard"
                onClick={() => setMobileMenuOpen(false)}
                className="bg-[#00CC68] text-black text-center py-3 rounded-full font-bold uppercase tracking-wider"
              >
                GO TO WORKSPACE
              </Link>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <Link
                  href="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="bg-white/10 text-white text-center py-3 rounded-full font-bold uppercase"
                >
                  SIGN IN
                </Link>
                <Link
                  href="/register"
                  onClick={() => setMobileMenuOpen(false)}
                  className="bg-[#00CC68] text-black text-center py-3 rounded-full font-bold uppercase"
                >
                  GET STARTED
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
