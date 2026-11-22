"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type RefObject } from "react";
import { authClient } from "@/lib/auth-client";

type Preview = { image: Blob; etag: string | null };
type DecodedPreview = { src: string; landscape: boolean; objectUrl: string | null };
const CACHE_NAME = "ob-paper-previews-v2";
const PREVIEW_STALE_TIME = 60 * 1000;
const MAX_WAIT_REQUESTS = 10;

export function paperPreviewQueryKey(viewerId: string | undefined, projectId: string | undefined) {
  return ["paper-preview", viewerId, projectId] as const;
}

async function openPreviewCache() {
  try {
    return await window.caches.open(CACHE_NAME);
  } catch {
    // The network and in-memory preview still work when Cache Storage is unavailable.
  }
}

function usePreviewVisibility(element: RefObject<HTMLDivElement | null>, enabled: boolean) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!enabled || visible || !element.current) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "256px" });
    observer.observe(element.current);
    return () => observer.disconnect();
  }, [element, enabled, visible]);
  return visible;
}

export function usePaperPreview(
  element: RefObject<HTMLDivElement | null>,
  projectId: string | undefined,
  template?: string | null,
) {
  const viewerId = authClient.useSession().data?.user.id;
  const enabled = Boolean(viewerId && projectId);
  const visible = usePreviewVisibility(element, enabled);
  const queryClient = useQueryClient();
  const queryKey = paperPreviewQueryKey(viewerId, projectId);
  const { data, isFetching } = useQuery<Preview | null>({
    queryKey,
    enabled: enabled && visible,
    // Editor saves and compiles invalidate the preview before this window expires.
    staleTime: (query) => query.state.data?.etag ? PREVIEW_STALE_TIME : 0,
    gcTime: 15 * 60 * 1000,
    refetchOnWindowFocus: true,
    retry: false,
    queryFn: async ({ signal }) => {
      if (!projectId || !viewerId) return null;
      const params = new URLSearchParams({ projectId, preview: "2" });
      const cacheKey = `/api/projects/preview?${params}&viewer=${encodeURIComponent(viewerId)}`;
      if (template) params.set("template", template);
      const url = `/api/projects/preview?${params}`;
      const cache = await openPreviewCache();
      let current = queryClient.getQueryData<Preview | null>(queryKey) ?? null;

      if (!current?.etag) {
        try {
          const cached = await cache?.match(cacheKey);
          const etag = cached?.headers.get("etag");
          if (cached && etag) {
            current = { image: await cached.blob(), etag };
            signal.throwIfAborted();
            queryClient.setQueryData(queryKey, current, { updatedAt: 1 });
          }
        } catch {
          // A storage error should not block revalidation.
        }
      }

      for (let attempt = 0; attempt <= MAX_WAIT_REQUESTS; attempt++) {
        const headers = current?.etag ? { "If-None-Match": current.etag } : undefined;
        const response = await fetch(attempt ? `${url}&wait=true` : url, {
          headers,
          signal,
          cache: "no-store",
        });
        if (response.status === 304 || response.status === 204) return current;
        if (response.status === 401 || response.status === 403 || response.status === 404) {
          await cache?.delete(cacheKey).catch(() => {});
          return null;
        }
        if (response.status === 202) continue;
        if (!response.ok || !response.headers.get("content-type")?.startsWith("image/")) return current;
        if (response.headers.get("x-preview-fallback") === "true") {
          if (!current) {
            current = { image: await response.blob(), etag: null };
            signal.throwIfAborted();
            queryClient.setQueryData(queryKey, current);
          } else {
            void response.body?.cancel().catch(() => {});
          }
          if (response.headers.get("x-preview-pending") === "true") continue;
          return current;
        }

        const etag = response.headers.get("etag");
        const image = await response.blob();
        signal.throwIfAborted();
        if (etag) {
          void cache?.put(cacheKey, new Response(image, {
            headers: { "Content-Type": image.type, ETag: etag },
          })).catch(() => {});
        }
        return { image, etag };
      }
      return current;
    },
  });

  return { blob: data?.image, isFetching };
}

export function useDecodedPaperPreview(blob: Blob | undefined, url?: string) {
  const [preview, setPreview] = useState<DecodedPreview | null>(null);
  const displayedUrl = useRef<string | null>(null);

  useEffect(() => () => {
    if (displayedUrl.current) URL.revokeObjectURL(displayedUrl.current);
    displayedUrl.current = null;
  }, []);

  useEffect(() => {
    if (!blob && !url) return;
    const src = blob ? URL.createObjectURL(blob) : url!;
    const image = new Image();
    let active = true;
    let published = false;
    image.src = src;
    image.decode().then(() => {
      if (!active) return;
      published = true;
      setPreview({ src, landscape: image.naturalWidth > image.naturalHeight * 1.15, objectUrl: blob ? src : null });
    }).catch(() => {
      if (blob) URL.revokeObjectURL(src);
    });
    return () => {
      active = false;
      if (blob && !published) URL.revokeObjectURL(src);
      if (blob && published && displayedUrl.current !== src) URL.revokeObjectURL(src);
    };
  }, [blob, url]);

  const current = blob || url ? preview : null;
  useEffect(() => {
    const nextUrl = current?.objectUrl ?? null;
    if (displayedUrl.current && displayedUrl.current !== nextUrl) {
      URL.revokeObjectURL(displayedUrl.current);
    }
    displayedUrl.current = nextUrl;
  }, [current]);

  return current;
}
