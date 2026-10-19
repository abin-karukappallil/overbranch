import React from "react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Create Account",
  description: "Create a free OverBranch account to write, compile, and collaborate on LaTeX documents.",
  alternates: {
    canonical: "/register",
  },
};

export default function RegisterLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <React.Fragment>{children}</React.Fragment>;
}
