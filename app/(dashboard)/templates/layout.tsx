import React from "react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Templates",
  description: "Explore free academic, thesis, resume, presentation, and journal LaTeX templates.",
};

export default function TemplatesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <React.Fragment>{children}</React.Fragment>;
}
