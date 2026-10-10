import React from "react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Dashboard",
  description: "Manage your LaTeX projects, documents, and collaboration on OverBranch.",
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <React.Fragment>{children}</React.Fragment>;
}
