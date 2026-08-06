import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { TRPCProvider } from "@/trpc/client";
import { ThemeProvider } from "@/providers/ThemeProvider";
import { Toaster } from "sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export const metadata: Metadata = {
  title: "OverBranch — Collaborative LaTeX Editor & Developer Workspace",
  description: "Next-generation cloud workspace with instant web environments and seamless Git collaboration.",
  keywords: ["OverBranch", "LaTeX Editor", "Collaborative Workspace", "Developer Tools", "Next.js", "TypeScript"],
  authors: [{ name: "OverBranch Team" }],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="scroll-smooth dark">
      <body className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased bg-background text-foreground min-h-screen selection:bg-indigo-500/20 selection:text-indigo-300`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <TRPCProvider>
            {children}
            <Toaster position="bottom-right" theme="dark" richColors />
          </TRPCProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
