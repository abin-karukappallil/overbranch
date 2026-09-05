import type { Metadata } from "next";
import { Archivo_Black, Space_Mono, Inter } from "next/font/google";
import "./globals.css";
import { TRPCProvider } from "@/trpc/client";
import { ThemeProvider } from "@/providers/ThemeProvider";
import { Toaster } from "sonner";

const archivoBlack = Archivo_Black({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-archivo",
});

const spaceMono = Space_Mono({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-space-mono",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: "OverBranch — 100% Free & Open-Source Agentic Latex code editor",
  description: "Your AI. Your Code. Your Infrastructure. OverBranch is a free, open-source, self-hostable Agentic Latex code editor.",
  keywords: ["OverBranch", "AI Platform", "Open Source", "Self-Hostable", "AI Workflows", "Developer Tools", "AI Infrastructure", "pdf to latex", "Ai latex code editor","pdf to latex code generator","overleaf alternative","best pdf to latex","ai pdf to latex","free pdf to latex"],
  authors: [{ name: "OverBranch Team" }],
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icon.png", type: "image/png" },
    ],
    apple: [
      { url: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  },
};

import { GuestMigrationListener } from "@/components/GuestMigrationListener";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="scroll-smooth dark">
      <body
        className={`${archivoBlack.variable} ${spaceMono.variable} ${inter.variable} font-sans antialiased bg-[#00CC68] text-black min-h-screen selection:bg-black selection:text-[#00CC68]`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <TRPCProvider>
            <GuestMigrationListener />
            {children}
            <Toaster position="top-right" theme="dark" richColors />
          </TRPCProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
