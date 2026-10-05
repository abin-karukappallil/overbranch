"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FileText,
  ArrowRight,
  ShieldCheck,
  Clock,
  RotateCw,
  Zap,
  ExternalLink,
  Gauge,
} from "lucide-react";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { authClient } from "@/lib/auth-client";
import { authFetch } from "@/lib/api-client";
import { ImportPdfDialog } from "@/components/pdf-import/ImportPdfDialog";

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

export default function ConvertPage() {
  const router = useRouter();
  const importedProjectId = useRef<string | null>(null);

  // Authenticated user check: logged in users should use the dashboard converter
  const { data: authSession, isPending: isAuthPending } = authClient.useSession();

  useEffect(() => {
    if (!isAuthPending && authSession?.user) {
      // Clean up stale guest token for logged-in users
      try {
        localStorage.removeItem("ob_guest_token");
        document.cookie = "ob_guest_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      } catch (_) {}
      router.replace("/dashboard?openPdfModal=true");
    }
  }, [authSession, isAuthPending, router]);

  // Session & Quota Status
  const [sessionLoading, setSessionLoading] = useState(true);
  const [quotaStatus, setQuotaStatus] = useState<any | null>(null);

  const fetchSessionStatus = async () => {
    if (authSession?.user) {
      setSessionLoading(false);
      return;
    }
    try {
      const res = await authFetch(`${BACKEND_URL}/api/guest/session`);
      if (res.ok) {
        const data = await res.json();
        setQuotaStatus(data);
        if (data.token && !authSession?.user) {
          document.cookie = `ob_guest_token=${data.token}; path=/; max-age=86400; SameSite=Lax`;
          localStorage.setItem("ob_guest_token", data.token);
        }
      }
    } catch (e) {
      console.warn("Could not load guest session:", e);
    } finally {
      setSessionLoading(false);
    }
  };

  useEffect(() => {
    fetchSessionStatus();
  }, []);

  const isQuotaReached = quotaStatus && !quotaStatus.allowed;

  if (isAuthPending || authSession?.user) {
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center text-zinc-400 gap-3">
        <RotateCw className="w-6 h-6 animate-spin text-indigo-400" />
        <p className="text-xs font-mono">
          {authSession?.user ? "Redirecting to Dashboard PDF Workspace..." : "Verifying session..."}
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col selection:bg-indigo-500/30 selection:text-indigo-400">
      {/* Top Navigation */}
      <header className="h-16 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md px-4 sm:px-8 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 hover:opacity-90 transition-opacity">
            <OverBranchLogo size="sm" colored showBeta />
          </Link>
          <div className="h-4 w-px bg-zinc-800 hidden sm:block" />
        </div>

        <div className="flex items-center gap-3">
          <a
            href="https://github.com/abin-karukappallil/overbranch/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-900 text-[11px] text-zinc-400 hover:text-amber-300 font-mono transition-colors"
            title="OverBranch is in active Beta — Report any bugs on GitHub Issues"
          >
            <span className="text-[9px] font-mono font-bold text-amber-300 bg-amber-400/10 border border-amber-400/20 px-1 py-0.5 rounded">BETA</span>
            <span>Report Bug</span>
          </a>
          <Link
            href="/login"
            className="text-xs font-mono text-zinc-400 hover:text-white transition-colors px-3 py-1.5 rounded-lg"
          >
            Sign In
          </Link>
          <Link
            href="/register"
            className="text-xs font-mono font-bold bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl shadow-sm shadow-indigo-500/20 border border-indigo-700 transition-all flex items-center gap-1.5"
          >
            <span>Create Account</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 flex flex-col justify-center">
        {/* Header Hero */}
        <div className="text-center space-y-3 mb-8">
          <h1 className="text-2xl sm:text-4xl font-archivo font-black uppercase tracking-tight text-white flex items-center justify-center gap-2.5 flex-wrap">
            <span>Convert a PDF to <span className="text-indigo-400">LaTeX</span></span>
            <span className="text-xs sm:text-sm font-mono font-black uppercase px-2 py-0.5 rounded bg-zinc-800 text-indigo-400 border border-zinc-700 tracking-wider">
              BETA
            </span>
          </h1>

          <p className="text-xs sm:text-sm text-zinc-400 max-w-xl mx-auto font-sans leading-relaxed">
            Text, font sizes, colors, positions, images and vector shapes are extracted from the PDF itself, and every page is rewritten as LaTeX by the same model as the AI copilot. Each page is compiled and compared with the original, and you see the measured similarity.
          </p>

          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-zinc-900 border border-zinc-800 text-[11px] font-mono text-zinc-400">
            <span className="text-indigo-400 font-bold">⚠️ Beta Feature:</span>
            <span>Encountering bugs or formatting issues? Please</span>
            <a
              href="https://github.com/abin-karukappallil/overbranch/issues"
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-400 underline font-bold"
            >
              report on GitHub Issues →
            </a>
          </div>
        </div>

        {/* Existing Active Project Banner */}
        {quotaStatus?.active_project && (
          <div className="mb-6 p-4 rounded-2xl bg-zinc-900/90 border border-indigo-500/30 shadow-lg flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-left">
              <div className="p-2.5 rounded-xl bg-indigo-500/15 border border-indigo-500/30 text-indigo-400">
                <FileText className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs font-mono text-indigo-400 uppercase font-bold tracking-wider">
                  Active Guest Project Found
                </div>
                <div className="text-sm font-archivo font-bold text-white">
                  {quotaStatus.active_project.name}
                </div>
                <div className="text-[11px] text-zinc-400 font-mono">
                  Expires in ~{Math.ceil(quotaStatus.active_project.seconds_remaining / 3600)}h
                </div>
              </div>
            </div>

            <Link
              href={`/editor/${quotaStatus.active_project.project_id}`}
              className="w-full sm:w-auto px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-mono font-bold text-xs rounded-xl shadow-sm shadow-indigo-500/20 border border-indigo-700 transition-all flex items-center justify-center gap-2"
            >
              <span>Resume in Editor</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>
        )}

        {/* Quota Exhausted Card */}
        {isQuotaReached ? (
          <div className="p-6 sm:p-8 rounded-3xl border border-amber-500/30 bg-zinc-900/90 shadow-2xl text-center space-y-5">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Clock className="w-7 h-7" />
            </div>

            <div className="space-y-2 max-w-md mx-auto">
              <h3 className="text-xl font-archivo font-black uppercase text-white">
                Daily Guest Limit Reached
              </h3>
              <p className="text-xs text-zinc-400 leading-relaxed font-sans">
                {quotaStatus?.reason || "Guest conversions are capped at 1 document per 24 hours per device to maintain GPU availability."}
              </p>
            </div>

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link
                href="/register"
                className="w-full sm:w-auto px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-mono font-bold text-xs uppercase tracking-wider shadow-sm shadow-indigo-500/20 border border-indigo-700 transition-all flex items-center justify-center gap-2"
              >
                <span>Create Free Account for Unlimited Access</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/login"
                className="w-full sm:w-auto px-5 py-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-mono text-xs border border-zinc-700 transition-colors"
              >
                Sign In
              </Link>
            </div>
          </div>
        ) : (
          /* Conversion panel (shared with the dashboard and editor importer) */
          <ImportPdfDialog
            inline
            open
            onOpenChange={() => {
              if (importedProjectId.current) router.push(`/editor/${importedProjectId.current}`);
            }}
            onCompleted={({ projectId }) => {
              // Quota is not re-fetched here so the report stays visible until the user opens the editor
              importedProjectId.current = projectId;
            }}
          />
        )}

        {/* Technical Architecture Guarantees */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-8">
          <div className="p-4 rounded-2xl border border-zinc-800/80 bg-zinc-900/50 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-white">
              <Zap className="w-3.5 h-3.5 text-indigo-400" />
              <span>Text Stays Text</span>
            </div>
            <p className="text-[11px] text-zinc-400 font-sans leading-relaxed">
              Text is never rasterized: it is set with the embedded font or the closest installed match, and every substitution is listed in the report.
            </p>
          </div>

          <div className="p-4 rounded-2xl border border-zinc-800/80 bg-zinc-900/50 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-white">
              <Gauge className="w-3.5 h-3.5 text-indigo-400" />
              <span>Measured Fidelity</span>
            </div>
            <p className="text-[11px] text-zinc-400 font-sans leading-relaxed">
              Each page is rendered and compared (SSIM + pixel difference) and repaired up to four times. Scores are shown per page; results are best-effort, not guaranteed identical.
            </p>
          </div>

          <div className="p-4 rounded-2xl border border-zinc-800/80 bg-zinc-900/50 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-white">
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
              <span>Seamless Migration</span>
            </div>
            <p className="text-[11px] text-zinc-400 font-sans leading-relaxed">
              Sign up at any time to automatically migrate your temporary guest project into your personal account with full edit history preserved.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
