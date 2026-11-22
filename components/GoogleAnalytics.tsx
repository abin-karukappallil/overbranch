"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import Script from "next/script";
import {
  COOKIE_PREFERENCES_CHANGED,
  COOKIE_PREFERENCES_KEY,
  readCookiePreferences,
} from "@/lib/cookie-preferences";

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    [key: `ga-disable-${string}`]: boolean | undefined;
  }
}

function pageData(pathname: string) {
  // Keep project ids, document titles, and query strings out of page views.
  const path = pathname.startsWith("/editor/") ? "/editor" : pathname;
  return {
    page_location: window.location.origin + path,
    page_path: path,
    page_title: path === "/" ? "Home" : path,
    page_referrer: "",
    ignore_referrer: true,
  };
}

export function GoogleAnalytics({ id }: { id: string }) {
  const pathname = usePathname();
  const [enabled, setEnabled] = useState(false);
  const configuredId = useRef<string | null>(null);
  const lastPath = useRef<string | null>(null);

  useEffect(() => {
    if (!id) return;
    const browser = window;

    function syncPreference() {
      const active = readCookiePreferences()?.analytics !== false;
      browser[`ga-disable-${id}`] = !active;
      if (active && configuredId.current !== id) {
        browser.dataLayer ??= [];
        browser.gtag ??= function () {
          browser.dataLayer?.push(arguments);
        };
        browser.gtag("consent", "default", {
          analytics_storage: "denied",
          ad_storage: "denied",
          ad_user_data: "denied",
          ad_personalization: "denied",
        });
        browser.gtag("set", pageData(browser.location.pathname));
        browser.gtag("js", new Date());
        browser.gtag("config", id, {
          send_page_view: false,
          allow_google_signals: false,
          allow_ad_personalization_signals: false,
        });
        configuredId.current = id;
      }
      if (!active) lastPath.current = null;
      setEnabled(active);
    }

    function syncAcrossTabs(event: StorageEvent) {
      if (event.key === COOKIE_PREFERENCES_KEY || event.key === null) syncPreference();
    }

    syncPreference();
    window.addEventListener(COOKIE_PREFERENCES_CHANGED, syncPreference);
    window.addEventListener("storage", syncAcrossTabs);
    return () => {
      window.removeEventListener(COOKIE_PREFERENCES_CHANGED, syncPreference);
      window.removeEventListener("storage", syncAcrossTabs);
    };
  }, [id]);

  useEffect(() => {
    if (!enabled || !pathname || lastPath.current === pathname) return;
    const browser = window;
    if (browser[`ga-disable-${id}`]) return;
    lastPath.current = pathname;

    const page = pageData(pathname);
    browser.gtag?.("set", page);
    browser.gtag?.("event", "page_view", { ...page, send_to: id });
  }, [enabled, id, pathname]);

  if (!id || !enabled) return null;
  return <Script strategy="afterInteractive" src={"https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id)} />;
}
