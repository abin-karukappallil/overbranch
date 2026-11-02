"use client";

/**
 * DownloadPackageButton — saves a finished import's package (main.tex, assets/, output.pdf,
 * report.md) as "<name>-latex.zip". The zip is fetched with authFetch and handed to the browser
 * as an object URL: the backend URL never goes into an href (the Bearer would not be sent).
 */

import React, { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { authFetch } from "@/lib/api-client";
import { BACKEND_URL } from "./usePdfConversionJob";

export function packageFileName(filename: string | null | undefined) {
  const base = (filename || "document").replace(/\.pdf$/i, "").trim() || "document";
  return `${base}-latex.zip`;
}

export async function downloadConversionPackage(jobId: string, fileName: string) {
  const res = await authFetch(`${BACKEND_URL}/api/convert/pdf/${jobId}/package.zip`);
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body?.detail?.message || body?.detail?.code || (typeof body?.detail === "string" ? body.detail : "");
    } catch {
      /* not JSON */
    }
    throw new Error(
      res.status === 404 ? "The package is not ready yet." : detail || `Download failed (${res.status}).`
    );
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Give the browser a moment to start reading the blob before it goes away.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function DownloadPackageButton({ jobId, filename }: { jobId: string; filename: string }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      type="button"
      variant="outline"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await downloadConversionPackage(jobId, packageFileName(filename));
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "Download failed.");
        } finally {
          setBusy(false);
        }
      }}
      className="h-8 px-3 text-xs border-[#23252A] bg-[#191A1B] text-[#F7F8F8] hover:bg-[#23252A] flex items-center gap-1.5"
    >
      {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
      <span>{busy ? "Preparing…" : "Download .zip"}</span>
    </Button>
  );
}
