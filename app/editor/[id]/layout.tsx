import React from "react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Editor",
  description: "Agentic LaTeX code editor workspace on OverBranch.",
};

export default function EditorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <React.Fragment>{children}</React.Fragment>;
}
