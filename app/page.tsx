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
import { getServerSession } from "@/lib/get-server-session";

export default async function HomePage() {
  const session = await getServerSession();
  const isAuthenticated = Boolean(session?.user);

  return (
    <div className="min-h-screen bg-[#00CC68] text-black selection:bg-black selection:text-[#00CC68] overflow-x-clip max-w-full font-sans antialiased">
      <LandingHeader initialIsAuthenticated={isAuthenticated} />

      <main>
        <LandingHero initialIsAuthenticated={isAuthenticated} />
        <BrandMarquee />
        <LandingIntroduction />
        <LandingFeatures />
        <LandingPdfToLatex initialIsAuthenticated={isAuthenticated} />
        <LandingTemplates />
        <LandingSelfHosting />
        <LandingOpenSource />
        <LandingFreeSection />
        <TechnicalMarquee />
        <LandingCTA initialIsAuthenticated={isAuthenticated} />
      </main>

      <LandingFooter />
    </div>
  );
}