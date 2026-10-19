import React from "react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PDF to LaTeX Converter — Free, Accurate & Instant",
  description: "Convert research papers, documents, tables, and math formulas from PDF to clean, editable LaTeX code instantly with OverBranch AI.",
  alternates: {
    canonical: "/convert",
  },
  openGraph: {
    title: "PDF to LaTeX Converter — OverBranch",
    description: "Convert research papers and documents from PDF to clean, editable LaTeX code instantly with OverBranch AI.",
    url: "/convert",
    type: "website",
  },
};

export default function ConvertLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <React.Fragment>{children}</React.Fragment>;
}
