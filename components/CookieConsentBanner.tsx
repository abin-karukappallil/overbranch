"use client";

import React, { useState, useEffect } from "react";
import { Cookie, ShieldCheck, Check, Settings2, ChevronDown, ChevronUp, Lock } from "lucide-react";

export interface CookieConsentData {
  status: "accepted" | "essential";
  analytics: boolean;
  timestamp: number;
}

const CONSENT_STORAGE_KEY = "overbranch_cookie_consent";
const CONSENT_COOKIE_NAME = "overbranch_cookie_consent";

export function getStoredCookieConsent(): CookieConsentData | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(CONSENT_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function CookieConsentBanner() {
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [analyticsEnabled, setAnalyticsEnabled] = useState(true);

  useEffect(() => {
    setMounted(true);
    const existing = getStoredCookieConsent();
    if (!existing) {
      const timer = setTimeout(() => {
        setVisible(true);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, []);

  const saveConsent = (status: "accepted" | "essential", analytics: boolean) => {
    const consentData: CookieConsentData = {
      status,
      analytics,
      timestamp: Date.now(),
    };

    try {
      localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(consentData));
      document.cookie = `${CONSENT_COOKIE_NAME}=${status}; path=/; max-age=31536000; SameSite=Lax`;
    } catch (e) {
      console.warn("Could not save cookie consent preference", e);
    }

    if (typeof window !== "undefined") {
      if (typeof (window as any).gtag === "function") {
        (window as any).gtag("consent", "update", {
          analytics_storage: analytics ? "granted" : "denied",
        });
      }
      window.dispatchEvent(
        new CustomEvent("cookie_consent_updated", { detail: consentData })
      );
    }

    setVisible(false);
  };

  const handleAcceptAll = () => {
    saveConsent("accepted", true);
  };

  const handleEssentialOnly = () => {
    saveConsent("essential", false);
  };

  const handleSaveCustom = () => {
    saveConsent(analyticsEnabled ? "accepted" : "essential", analyticsEnabled);
  };

  if (!mounted || !visible) return null;

  return (
    <div
      role="region"
      aria-label="Cookie consent banner"
      className="fixed bottom-3 left-3 right-3 sm:left-auto sm:right-6 sm:bottom-6 sm:max-w-md z-50 animate-in fade-in slide-in-from-bottom-5 duration-300 font-sans"
    >
      <div className="p-4 sm:p-5 rounded-2xl bg-white/95 dark:bg-[#141519]/95 backdrop-blur-md border border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] shadow-2xl space-y-3.5">
        {/* Header */}
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-50 dark:bg-[#10B981]/15 text-emerald-600 dark:text-[#10B981] flex items-center justify-center shrink-0 border border-emerald-200/60 dark:border-[#10B981]/30">
            <Cookie className="w-5 h-5" />
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <h3 className="font-archivo font-bold text-sm text-slate-900 dark:text-[#E2E4E9]">
                Cookie & Privacy Consent
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 dark:bg-[#22242C] text-slate-500 dark:text-[#9E9E9E] border border-slate-200 dark:border-[#282A30]">
                OverBranch
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-[#9E9E9E] leading-relaxed">
              We use essential cookies to maintain your authenticated LaTeX workspace and compile sessions. With your permission, we also use analytical cookies to improve platform performance.
            </p>
          </div>
        </div>

        {/* Expandable Preferences Section */}
        {showDetails && (
          <div className="pt-2 pb-1 border-t border-slate-200/70 dark:border-[#282A30]/70 space-y-2.5 text-xs font-mono">
            {/* Essential Cookies Row */}
            <div className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-[#1A1C22] border border-slate-200/60 dark:border-[#282A30]/60">
              <div className="space-y-0.5 pr-2">
                <div className="flex items-center gap-1.5 font-medium text-slate-900 dark:text-[#E2E4E9]">
                  <Lock className="w-3 h-3 text-emerald-600 dark:text-[#10B981]" />
                  <span>Essential & Security</span>
                </div>
                <p className="text-[10px] text-slate-500 dark:text-[#8A8F98]">
                  Required for login, session state, and editor caching.
                </p>
              </div>
              <span className="text-[10px] font-bold uppercase text-emerald-600 dark:text-[#10B981] shrink-0">
                Always Active
              </span>
            </div>

            {/* Analytics Cookies Row */}
            <div className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-[#1A1C22] border border-slate-200/60 dark:border-[#282A30]/60">
              <div className="space-y-0.5 pr-2">
                <div className="flex items-center gap-1.5 font-medium text-slate-900 dark:text-[#E2E4E9]">
                  <ShieldCheck className="w-3 h-3 text-slate-600 dark:text-[#9E9E9E]" />
                  <span>Analytics & Insights</span>
                </div>
                <p className="text-[10px] text-slate-500 dark:text-[#8A8F98]">
                  Measures feature usage and error diagnostics.
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer shrink-0">
                <input
                  type="checkbox"
                  checked={analyticsEnabled}
                  onChange={(e) => setAnalyticsEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-8 h-4 bg-slate-200 dark:bg-[#282A30] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-emerald-600 dark:peer-checked:bg-[#10B981]"></div>
              </label>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 pt-1">
          <button
            type="button"
            onClick={() => setShowDetails(!showDetails)}
            className="text-[11px] font-mono text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] flex items-center justify-center sm:justify-start gap-1 py-1 cursor-pointer transition-colors"
          >
            <Settings2 className="w-3 h-3" />
            <span>{showDetails ? "Hide options" : "Customize"}</span>
            {showDetails ? (
              <ChevronUp className="w-3 h-3" />
            ) : (
              <ChevronDown className="w-3 h-3" />
            )}
          </button>

          <div className="flex items-center gap-2">
            {showDetails ? (
              <button
                type="button"
                onClick={handleSaveCustom}
                className="flex-1 sm:flex-initial px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 dark:bg-[#10B981] dark:hover:bg-[#059669] text-white font-archivo font-bold text-xs cursor-pointer transition-all shadow-sm flex items-center justify-center gap-1.5"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Save Choice</span>
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={handleEssentialOnly}
                  className="flex-1 sm:flex-initial px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-[#1E2026] dark:hover:bg-[#282A30] text-slate-700 dark:text-[#C5C8D0] font-mono font-medium text-xs border border-slate-200 dark:border-[#282A30] cursor-pointer transition-colors text-center"
                >
                  Essential Only
                </button>
                <button
                  type="button"
                  onClick={handleAcceptAll}
                  className="flex-1 sm:flex-initial px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 dark:bg-[#10B981] dark:hover:bg-[#059669] text-white font-archivo font-bold text-xs cursor-pointer transition-all shadow-sm text-center"
                >
                  Accept All
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
