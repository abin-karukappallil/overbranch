import React from "react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Projects",
  description: "View, organize, and manage all your LaTeX projects on OverBranch.",
};

export default function ProjectsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <React.Fragment>{children}</React.Fragment>;
}
