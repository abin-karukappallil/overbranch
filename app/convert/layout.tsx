import React from "react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PDF to LaTeX Converter",
  description: "Convert research papers, documents, and math formulas from PDF to clean, editable LaTeX instantly.",
};

export default function ConvertLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <React.Fragment>{children}</React.Fragment>;
}
