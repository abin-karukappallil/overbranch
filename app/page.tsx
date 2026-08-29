"use client";

import React from "react";
import { LandingHeader } from "@/components/landing/Header";
import { LandingHero } from "@/components/landing/Hero";
import { BrandMarquee } from "@/components/landing/BrandMarquee";
import { LandingIntroduction } from "@/components/landing/Introduction";
import { LandingPdfToLatex } from "@/components/landing/PdfToLatexSection";
import { LandingTemplates } from "@/components/landing/TemplatesSection";
import { LandingFeatures } from "@/components/landing/Features";
import { LandingSelfHosting } from "@/components/landing/SelfHosting";
import { LandingOpenSource } from "@/components/landing/OpenSourceSection";
import { LandingFreeSection } from "@/components/landing/FreeSection";
import { TechnicalMarquee } from "@/components/landing/TechnicalMarquee";
import { LandingCTA } from "@/components/landing/CTASection";
import { LandingFooter } from "@/components/landing/Footer";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[#00CC68] text-black selection:bg-black selection:text-[#00CC68] overflow-x-clip max-w-full font-sans antialiased">
      <LandingHeader />

      <main>
        <LandingHero />
        <BrandMarquee />
        <LandingIntroduction />
        <LandingPdfToLatex />
        <LandingTemplates />
        <LandingFeatures />
        <LandingSelfHosting />
        <LandingOpenSource />
        <LandingFreeSection />
        <TechnicalMarquee />
        <LandingCTA />
      </main>

      <LandingFooter />
    </div>
  );
}