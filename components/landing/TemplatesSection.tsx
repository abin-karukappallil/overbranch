"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Sparkles,
  ArrowRight,
  Presentation,
  FileText,
  UserCheck,
  GraduationCap,
  Mail,
  BookOpen,
} from "lucide-react";

interface TemplateItem {
  id: string;
  name: string;
  category: "presentation" | "paper" | "resume" | "letter" | "thesis";
  categoryLabel: string;
  description: string;
  tags: string[];
  docClass: string;
  accent: string;
}

const TEMPLATES: TemplateItem[] = [
  {
    id: "nordlight",
    name: "Nordlight 16:9 Presentation",
    category: "presentation",
    categoryLabel: "Beamer Deck",
    description: "Modern widescreen presentation deck featuring sleek dark canvas, modular columns, and crisp syntax blocks.",
    tags: ["BEAMER", "16:9 RATIO", "CODE BLOCKS", "ACADEMIC"],
    docClass: "beamer",
    accent: "border-sky-500/40 text-sky-400",
  },
  {
    id: "ieee",
    name: "IEEE Conference Proceedings",
    category: "paper",
    categoryLabel: "Research Paper",
    description: "Standard double-column IEEEtran template pre-wired for mathematical theorems, vector figures, and BibTeX citations.",
    tags: ["IEEE TRAN", "TWO-COLUMN", "BIBTEX", "CONFERENCE"],
    docClass: "IEEEtran",
    accent: "border-emerald-500/40 text-emerald-400",
  },
  {
    id: "deedy",
    name: "Deedy Modern Developer CV",
    category: "resume",
    categoryLabel: "Resume / CV",
    description: "Ultra clean, ATS-optimized single-page resume layout engineered for software engineers, ML researchers, and designers.",
    tags: ["ATS-FRIENDLY", "1-PAGE CV", "EXPERIENCE", "SKILLS"],
    docClass: "article",
    accent: "border-purple-500/40 text-purple-400",
  },
  {
    id: "phd-thesis",
    name: "University PhD Dissertation",
    category: "thesis",
    categoryLabel: "Thesis & Books",
    description: "Comprehensive multi-chapter dissertation setup with dynamic list of figures, tables, appendices, and index layout.",
    tags: ["BOOK CLASS", "MULTI-CHAPTER", "TOC & LOF", "DISSERTATION"],
    docClass: "report",
    accent: "border-amber-500/40 text-amber-400",
  },
  {
    id: "formal-notice",
    name: "Executive Notice & Duty Leave",
    category: "letter",
    categoryLabel: "Formal Letter",
    description: "Professional formal correspondence with customizable heading box, address hierarchy, and official signature block.",
    tags: ["LETTERHEAD", "SIGNATURE", "OFFICIAL", "DUTY LEAVE"],
    docClass: "letter",
    accent: "border-rose-500/40 text-rose-400",
  },
  {
    id: "lab-report",
    name: "Modern Engineering Lab Report",
    category: "paper",
    categoryLabel: "Assignments",
    description: "Structured academic coursework template with derivation environments, code listing boxes, and data tables.",
    tags: ["COURSEWORK", "DERIVATIONS", "LAB REPORT", "MATRICES"],
    docClass: "article",
    accent: "border-teal-500/40 text-teal-400",
  },
];

const CATEGORIES = [
  { id: "all", label: "ALL TEMPLATES" },
  { id: "presentation", label: "PRESENTATIONS (PPT)" },
  { id: "paper", label: "RESEARCH PAPERS" },
  { id: "resume", label: "RESUMES & CVS" },
  { id: "letter", label: "FORMAL LETTERS" },
  { id: "thesis", label: "THESES & DISSERTATIONS" },
];

export function LandingTemplates() {
  const [selectedCategory, setSelectedCategory] = useState("all");

  const filtered = selectedCategory === "all"
    ? TEMPLATES
    : TEMPLATES.filter((t) => t.category === selectedCategory);

  return (
    <section
      id="templates"
      className="bg-black text-white py-24 px-4 sm:px-8 lg:px-16 border-b-2 border-white/20 select-none relative"
    >
      <div className="max-w-7xl mx-auto space-y-16">
        {/* Section Title & Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div className="space-y-3 max-w-3xl">
            <div className="inline-flex items-center gap-2 font-mono text-xs sm:text-sm font-bold text-[#00CC68] tracking-widest uppercase">
              <Sparkles className="w-4 h-4 text-[#00CC68]" />
              <span>03 // PRE-CONFIGURED LATEX VAULT</span>
            </div>
            <h2 className="font-archivo font-black uppercase text-3xl sm:text-5xl lg:text-7xl text-white tracking-[-0.04em] leading-[0.92]">
              CURATED TEMPLATES.
            </h2>
            <p className="font-sans text-base sm:text-xl text-zinc-300 leading-relaxed pt-2">
              Skip hours of arcane package debugging. Clone production-tested templates for research papers, seminar slides, thesis dissertations, and resumes.
            </p>
          </div>

          <Link
            href="/templates"
            className="inline-flex items-center gap-3 bg-white text-black px-6 py-3.5 rounded-full font-mono text-xs sm:text-sm font-bold uppercase tracking-wider border-2 border-black hover:bg-[#00CC68] hover:text-black shadow-[4px_4px_0px_0px_#00CC68] hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none transition-all duration-150 shrink-0 self-start md:self-end"
          >
            <span>EXPLORE FULL GALLERY</span>
            <ArrowRight className="w-4 h-4 stroke-[3]" />
          </Link>
        </div>

        {/* Filter Buttons */}
        <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none font-mono text-xs font-bold uppercase">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-4 py-2 rounded-full border transition-all duration-150 whitespace-nowrap cursor-pointer ${
                selectedCategory === cat.id
                  ? "bg-[#00CC68] text-black border-[#00CC68] shadow-[3px_3px_0px_0px_#ffffff]"
                  : "bg-white/5 border-white/20 text-zinc-400 hover:text-white hover:bg-white/10"
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Templates Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
          {filtered.map((tmpl) => (
            <Link
              key={tmpl.id}
              href="/templates"
              className="group p-6 sm:p-7 rounded-3xl border-2 border-white/20 bg-zinc-950 hover:border-[#00CC68] transition-all duration-200 flex flex-col justify-between space-y-6 shadow-xl hover:shadow-[0_0_30px_rgba(0,204,104,0.12)] cursor-pointer"
            >
              <div className="space-y-4">
                {/* Top Badge & Class */}
                <div className="flex items-center justify-between">
                  <span className={`px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider bg-white/5 border ${tmpl.accent}`}>
                    {tmpl.categoryLabel}
                  </span>
                  <span className="font-mono text-[11px] text-zinc-400">
                    \{tmpl.docClass}
                  </span>
                </div>

                {/* Title & Description */}
                <div className="space-y-2">
                  <h3 className="font-archivo font-bold uppercase text-xl sm:text-2xl text-white group-hover:text-[#00CC68] transition-colors leading-tight">
                    {tmpl.name}
                  </h3>
                  <p className="font-sans text-xs sm:text-sm text-zinc-400 leading-relaxed">
                    {tmpl.description}
                  </p>
                </div>
              </div>

              {/* Bottom Tags and Action Link */}
              <div className="space-y-4 pt-4 border-t border-white/10">
                <div className="flex flex-wrap gap-1.5">
                  {tmpl.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-white/5 text-zinc-400 group-hover:text-zinc-200 uppercase"
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                <div className="flex items-center justify-between text-xs font-mono font-bold text-white group-hover:text-[#00CC68] pt-1">
                  <span>USE TEMPLATE</span>
                  <span className="group-hover:translate-x-1.5 transition-transform duration-150">
                    →
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>

        {/* Bottom Banner Callout */}
        <div className="p-8 sm:p-10 rounded-3xl bg-zinc-950 border-2 border-white/20 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="space-y-2 text-center md:text-left">
            <h3 className="font-archivo font-black uppercase text-2xl sm:text-3xl text-white tracking-tight">
              NEED A CUSTOM LATEX TEMPLATE?
            </h3>
            <p className="font-sans text-sm text-zinc-400 max-w-2xl">
              Describe your seminar topic, conference paper guidelines, or resume style to our built-in Agentic AI. It configures the packages, styles, and architecture automatically.
            </p>
          </div>

          <Link
            href="/dashboard"
            className="inline-flex items-center gap-3 bg-[#00CC68] text-black px-7 py-4 rounded-full font-mono text-xs sm:text-sm font-bold uppercase tracking-wider border-2 border-black shadow-[4px_4px_0px_0px_#ffffff] hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none transition-all duration-150 shrink-0"
          >
            <span>LAUNCH IDE WORKSPACE</span>
            <ArrowRight className="w-4 h-4 stroke-[3]" />
          </Link>
        </div>
      </div>
    </section>
  );
}
