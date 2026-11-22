"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Cookie, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { OPEN_COOKIE_SETTINGS, readCookiePreferences, saveCookiePreferences } from "@/lib/cookie-preferences";

export function CookieConsentBanner({ analyticsAvailable }: { analyticsAvailable: boolean }) {
  const [view, setView] = useState<"notice" | "settings" | null>(null);
  const [analytics, setAnalytics] = useState(true);
  const panel = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (!readCookiePreferences()) setView("notice");
    }, 500);

    function openSettings() {
      window.clearTimeout(timer);
      trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setAnalytics(readCookiePreferences()?.analytics ?? true);
      setView("settings");
    }

    window.addEventListener(OPEN_COOKIE_SETTINGS, openSettings);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener(OPEN_COOKIE_SETTINGS, openSettings);
    };
  }, []);

  useEffect(() => {
    if (view === "settings") panel.current?.focus();
  }, [view]);

  function close() {
    setView(null);
    trigger.current?.focus();
    trigger.current = null;
  }

  function save(active: boolean) {
    saveCookiePreferences(active);
    close();
  }

  if (!view) return null;

  return (
    <section
      ref={panel}
      tabIndex={-1}
      aria-labelledby="cookie-settings-title"
      onKeyDown={(event) => { if (event.key === "Escape") close(); }}
      className="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-50 grid gap-4 rounded-2xl border border-ob-line bg-ob-card p-4 text-ob-text shadow-[0_12px_40px_rgba(0,0,0,0.2)] outline-none sm:left-auto sm:right-5 sm:w-[26rem] sm:p-5"
    >
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-ob-accent/10 text-ob-accent">
          <Cookie className="size-4.5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <h2 id="cookie-settings-title" className="text-sm font-semibold">Cookie settings</h2>
          <p className="text-[13px] leading-5 text-ob-text-2">
            Essential cookies keep you signed in and maintain your session.
            {analyticsAvailable && " We use Google Analytics to measure visits without analytics cookies. You can turn measurement off at any time."}
          </p>
          <Link href="/terms#cookies" className="inline-block text-xs font-medium text-ob-accent underline underline-offset-4">
            How cookies and analytics work
          </Link>
        </div>
        <button
          type="button"
          aria-label="Close cookie settings"
          className="-mr-1 flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-ob-muted hover:bg-ob-raised hover:text-ob-text"
          onClick={close}
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>

      {view === "settings" && analyticsAvailable && (
        <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg bg-ob-raised px-3 py-2.5 text-sm font-medium">
          Analytics
          <input
            type="checkbox"
            checked={analytics}
            onChange={(event) => setAnalytics(event.target.checked)}
            className="size-4 accent-ob-accent"
          />
        </label>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        {view === "notice" && analyticsAvailable && (
          <Button variant="ob-secondary" size="sm" onClick={() => save(false)}>
            Turn off analytics
          </Button>
        )}
        <Button
          variant="ob-primary"
          size="sm"
          onClick={() => save(view === "settings" ? analytics : readCookiePreferences()?.analytics ?? true)}
        >
          {view === "settings" ? "Save preferences" : "Accept cookies"}
        </Button>
      </div>
    </section>
  );
}
