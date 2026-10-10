"use client";

import { useEffect, Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import Script from "next/script";

function GoogleAnalyticsTracker({ id }: { id: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (!pathname || typeof window === "undefined") return;

    const url = pathname + (searchParams?.toString() ? `?${searchParams.toString()}` : "");

    // Allow Next.js route metadata or page effect to update document.title
    const timer = setTimeout(() => {
      if (typeof (window as any).gtag === "function") {
        (window as any).gtag("event", "page_view", {
          page_title: document.title,
          page_location: window.location.href,
          page_path: url,
          send_to: id,
        });
      }
    }, 150);

    return () => clearTimeout(timer);
  }, [pathname, searchParams, id]);

  return null;
}

export function GoogleAnalytics({ gaId }: { gaId?: string }) {
  const id = gaId || process.env.NEXT_PUBLIC_GA_ID || "";

  if (!id) return null;

  return (
    <>
      <Script
        strategy="afterInteractive"
        src={`https://www.googletagmanager.com/gtag/js?id=${id}`}
      />
      <Script
        id="google-analytics"
        strategy="afterInteractive"
        dangerouslySetInnerHTML={{
          __html: `
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag("js", new Date());
            gtag("config", "${id}", {
              page_path: window.location.pathname,
              send_page_view: true,
            });
          `,
        }}
      />
      <Suspense fallback={null}>
        <GoogleAnalyticsTracker id={id} />
      </Suspense>
    </>
  );
}
