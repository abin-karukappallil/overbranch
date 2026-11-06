import React from "react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PDF to LaTeX Converter — Free, Editable LaTeX",
  description: "Convert research papers, documents, tables, and math formulas from PDF to editable LaTeX with OverBranch AI. The layout follows the original as closely as possible.",
  alternates: {
    canonical: "/convert",
  },
  openGraph: {
    title: "PDF to LaTeX Converter — OverBranch",
    description: "Convert research papers and documents from PDF to editable LaTeX with OverBranch AI — closest match to the original layout.",
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
