import React from "react";

/**
 * A small sheet of proof paper, drawn in code, whose layout follows the project's template type.
 * It sketches the kind of document, it is not a preview of this document. Off-white on both themes,
 * and the only place in the app with crop marks.
 *
 *   <PaperSheet template={project.template} seed={project.id} />
 *   <PaperSheet variant="beamer" size="sm" />
 *   <PaperSheet variant="blank" />
 */
export type PaperVariant = "article" | "ieee" | "beamer" | "thesis" | "assignment" | "report" | "blank";
type PaperSize = "sm" | "md" | "lg";

/** Which sketch fits a project's template name. Anything unknown, "None" included, is a plain article. */
export function paperVariantFor(template: string | null | undefined): PaperVariant {
  const t = (template || "").toLowerCase();
  if (/ieee|acm|conference|journal|paper/.test(t)) return "ieee";
  if (/beamer|slide|deck|presentation|lecture|talk|pitch/.test(t)) return "beamer";
  if (/thesis|dissertation/.test(t)) return "thesis";
  if (/assignment|homework|problem/.test(t)) return "assignment";
  if (/seminar|report/.test(t)) return "report";
  return "article";
}

// Width of the sheet in px. The 12px of crop margin around it is extra.
const PORTRAIT_WIDTH: Record<PaperSize, number> = { sm: 56, md: 96, lg: 132 };
const LANDSCAPE_WIDTH: Record<PaperSize, number> = { sm: 80, md: 136, lg: 184 };

// Drawing colours are real content, like syntax colours, so they stay raw and do not follow the theme.
const INK = "#26241f";
const GREY = "#7f7b72";
const FAINT = "#b3afa4";
const WASH = "#e9e6db";
const RUBRIC = "#a23a2a";
const SLATE = "#2b3440";

// A small stable number from the project id, so two IEEE papers do not read as clones.
function hash(seed: string): number {
  let h = 7;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return h;
}

function Bar({ x, y, w, h = 2, fill = FAINT }: { x: number; y: number; w: number; h?: number; fill?: string }) {
  return <rect x={x} y={y} width={w} height={h} fill={fill} />;
}

function Centred({ cx, y, w, h = 2, fill = GREY }: { cx: number; y: number; w: number; h?: number; fill?: string }) {
  return <rect x={cx - w / 2} y={y} width={w} height={h} fill={fill} />;
}

/** A justified paragraph: every line runs to the measure, the last one stops short. */
function Para({
  x,
  y,
  w,
  lines,
  step = 6,
  h = 2,
  last = 0.6,
  fill = FAINT,
  indent = 0,
}: {
  x: number;
  y: number;
  w: number;
  lines: number;
  step?: number;
  h?: number;
  last?: number;
  fill?: string;
  indent?: number;
}) {
  return (
    <>
      {Array.from({ length: lines }, (_, i) => {
        const isFirst = i === 0;
        const isLast = i === lines - 1;
        const left = isFirst ? indent : 0;
        return <Bar key={i} x={x + left} y={y + i * step} w={(isLast ? w * last : w) - left} h={h} fill={fill} />;
      })}
    </>
  );
}

function Article({ n }: { n: number }) {
  const x = 22;
  const w = 104;
  const a = 5 + (n % 3);
  return (
    <>
      <Centred cx={74} y={24} w={72 + (n % 12)} h={5.5} fill={INK} />
      <Centred cx={74} y={35} w={38} h={2.5} />
      <Centred cx={74} y={41} w={22} h={2} fill={FAINT} />
      <Bar x={x} y={56} w={40 + (n % 10)} h={3.5} fill={INK} />
      <Para x={x} y={65} w={w} lines={a} indent={6} last={0.5 + (n % 4) / 10} />
      <Bar x={x} y={73 + a * 6} w={32 + (n % 16)} h={3.5} fill={INK} />
      <Para x={x} y={82 + a * 6} w={w} lines={15 - a} indent={6} last={0.72} />
      <Centred cx={74} y={194} w={4} h={2} />
    </>
  );
}

function Ieee({ n }: { n: number }) {
  const left = 14;
  const col = 56;
  const right = left + col + 8;
  const figH = 26 + (n % 3) * 4;
  return (
    <>
      <Centred cx={74} y={14} w={104} h={5} fill={INK} />
      <Centred cx={74} y={22} w={56 + (n % 24)} h={5} fill={INK} />
      <Bar x={26} y={33} w={26} h={2} fill={GREY} />
      <Bar x={61} y={33} w={26} h={2} fill={GREY} />
      <Bar x={96} y={33} w={26} h={2} fill={GREY} />
      <Bar x={32} y={38} w={14} h={1.6} />
      <Bar x={67} y={38} w={14} h={1.6} />
      <Bar x={102} y={38} w={14} h={1.6} />

      {/* Left column: abstract, then the first section */}
      <Para x={left} y={48} w={col} lines={7} step={4.4} h={1.7} fill={GREY} last={0.7} />
      <Centred cx={left + col / 2} y={82} w={26} h={2.4} fill={INK} />
      <Para x={left} y={89} w={col} lines={25} step={4.4} h={1.7} last={0.92} />

      {/* Right column: a figure, then text */}
      <rect x={right} y={48} width={col} height={figH} fill={WASH} />
      <polyline
        points={`${right + 5},${48 + figH - 5} ${right + 18},${48 + figH - 11} ${right + 32},${48 + figH - 9} ${right + 50},${48 + 6}`}
        fill="none"
        stroke={RUBRIC}
        strokeWidth={1.4}
      />
      <Centred cx={right + col / 2} y={51 + figH} w={36} h={1.6} />
      <Para x={right} y={58 + figH} w={col} lines={8} step={4.4} h={1.7} last={0.8} />
      <Centred cx={right + col / 2} y={96 + figH} w={22} h={2.4} fill={INK} />
      <Para x={right} y={103 + figH} w={col} lines={Math.floor((196 - 103 - figH) / 4.4)} step={4.4} h={1.7} last={0.9} />
    </>
  );
}

function Beamer({ n }: { n: number }) {
  // viewBox is 210 by 132, a 16:10 slide
  return (
    <>
      <rect x={22} y={24} width={166} height={42} rx={4} fill={SLATE} />
      <Centred cx={105} y={35} w={108 + (n % 24)} h={8} fill="#f6f4ec" />
      <Centred cx={105} y={50} w={64} h={3.5} fill="#a9b1bb" />
      <Centred cx={105} y={78} w={50} h={4} fill={INK} />
      <Centred cx={105} y={88} w={72} h={3} fill={GREY} />
      <Centred cx={105} y={96} w={28} h={3} fill={FAINT} />
      <rect x={0} y={118} width={210} height={14} fill={SLATE} />
      <rect x={0} y={118} width={70} height={14} fill="#3b4654" />
      <Bar x={10} y={123.5} w={44} h={3} fill="#c9ced5" />
      <Bar x={84} y={123.5} w={66} h={3} fill="#a9b1bb" />
      <Bar x={186} y={123.5} w={14} h={3} fill="#a9b1bb" />
    </>
  );
}

function Thesis({ n }: { n: number }) {
  return (
    <>
      <circle cx={74} cy={38} r={13} fill="none" stroke={INK} strokeWidth={1.2} />
      <circle cx={74} cy={38} r={9.5} fill="none" stroke={INK} strokeWidth={0.6} />
      <path d="M74 31.5l4.5 3v6.5l-4.5 3-4.5-3v-6.5z" fill={RUBRIC} />
      <Centred cx={74} y={68} w={92} h={5.5} fill={INK} />
      <Centred cx={74} y={78} w={102} h={5.5} fill={INK} />
      <Centred cx={74} y={88} w={48 + (n % 28)} h={5.5} fill={INK} />
      <Centred cx={74} y={104} w={28} h={1} fill={RUBRIC} />
      <Centred cx={74} y={114} w={44} h={3} fill={GREY} />
      <Centred cx={74} y={136} w={78} h={2} />
      <Centred cx={74} y={142} w={92} h={2} />
      <Centred cx={74} y={148} w={56} h={2} />
      <Centred cx={74} y={176} w={62} h={2.6} fill={GREY} />
      <Centred cx={74} y={184} w={16} h={2.2} />
    </>
  );
}

function Assignment({ n }: { n: number }) {
  const x = 18;
  const w = 112;
  const body = x + 13;
  const measure = w - 13;
  const Numeral = ({ y, children }: { y: number; children: string }) => (
    <text x={x} y={y} fontFamily="var(--font-newsreader), Georgia, serif" fontSize={11} fontWeight={500} fill={RUBRIC}>
      {children}
    </text>
  );
  return (
    <>
      <Bar x={x} y={18} w={44} h={3} fill={INK} />
      <Bar x={x} y={24.5} w={28} h={2} fill={GREY} />
      <Bar x={x + w - 26} y={18} w={26} h={2} fill={GREY} />
      <Bar x={x + w - 18} y={24.5} w={18} h={2} fill={GREY} />
      <Bar x={x} y={33} w={w} h={1} fill={INK} />

      <Numeral y={53}>1.</Numeral>
      <Para x={body} y={46} w={measure} lines={3} last={0.55 + (n % 3) / 10} />
      <Centred cx={74} y={68} w={46} h={3} fill={GREY} />

      <Numeral y={92}>2.</Numeral>
      <Para x={body} y={85} w={measure} lines={2} last={0.8} />
      <Bar x={body + 4} y={100} w={60} h={2} />
      <Bar x={body + 4} y={107} w={72} h={2} />
      <Bar x={body + 4} y={114} w={44} h={2} />

      <Numeral y={138}>3.</Numeral>
      <Para x={body} y={131} w={measure} lines={3} last={0.4} />
      <Centred cx={74} y={153} w={58} h={3} fill={GREY} />

      <Numeral y={178}>4.</Numeral>
      <Para x={body} y={171} w={measure} lines={2} last={0.66} />
    </>
  );
}

function Report({ n }: { n: number }) {
  const x = 22;
  const w = 104;
  const fig = 70;
  return (
    <>
      <text x={x} y={31} fontFamily="var(--font-newsreader), Georgia, serif" fontSize={14} fontWeight={500} fill={RUBRIC}>
        1
      </text>
      <Bar x={x + 12} y={21} w={56 + (n % 22)} h={7} fill={INK} />
      <Para x={x} y={42} w={w} lines={5} indent={6} last={0.7} />
      <rect x={x + (w - fig) / 2} y={78} width={fig} height={46} fill={WASH} />
      <g stroke={INK} strokeWidth={0.7} fill="none">
        <path d={`M${x + 24} 84v34h60`} />
      </g>
      {[0, 1, 2, 3, 4].map((i) => {
        const hs = [8, 13, 20, 16 + (n % 4), 27];
        return <rect key={i} x={x + 29 + i * 11} y={118 - hs[i]} width={6} height={hs[i]} fill={i === 4 ? RUBRIC : GREY} />;
      })}
      <Centred cx={74} y={129} w={44} h={1.8} />
      <Para x={x} y={141} w={w} lines={4} last={0.86} />
      <Bar x={x} y={169} w={36} h={3.2} fill={INK} />
      <Para x={x} y={177} w={w} lines={3} last={0.5} />
    </>
  );
}

const CORNERS = [
  { className: "top-0 left-0", d: "M10.5 0v7M0 10.5h7" },
  { className: "top-0 right-0", d: "M1.5 0v7M12 10.5H5" },
  { className: "bottom-0 left-0", d: "M10.5 12V5M0 1.5h7" },
  { className: "bottom-0 right-0", d: "M1.5 12V5M12 1.5H5" },
];

const PREVIEW_CACHE_NAME = "ob-paper-previews-v1";
// In-memory instant cache (0ms lookup, survives in-app route transitions)
const previewMemoryCache = new Map<string, string>();
const previewLandscapeCache = new Map<string, boolean>();

/** Speculatively pre-warm a project preview into the browser & memory cache */
export function preloadPaperPreview(
  projectId?: string,
  updatedAt?: string | number | Date | null,
  template?: string | null
) {
  if (typeof window === "undefined" || !projectId) return;
  const targetUrl = `/api/projects/preview?projectId=${encodeURIComponent(projectId)}${
    updatedAt ? `&v=${encodeURIComponent(String(updatedAt))}` : ""
  }${template ? `&template=${encodeURIComponent(template)}` : ""}`;
  const key = `${projectId}:${updatedAt || ""}`;
  if (previewMemoryCache.has(key)) return;

  const img = new Image();
  img.src = targetUrl;
  img.onload = () => {
    previewMemoryCache.set(key, targetUrl);
    if (img.naturalWidth && img.naturalHeight && img.naturalWidth > img.naturalHeight * 1.15) {
      previewLandscapeCache.set(key, true);
    }
  };
}

export function PaperSheet({
  template,
  variant,
  seed = "",
  size = "md",
  className = "",
  projectId,
  previewUrl,
  updatedAt,
}: {
  template?: string | null;
  /** Overrides `template`, for places with no project behind them. */
  variant?: PaperVariant;
  /** Project id, so sheets of the same type differ slightly. */
  seed?: string;
  size?: PaperSize;
  className?: string;
  projectId?: string;
  previewUrl?: string;
  updatedAt?: string | number | Date | null;
}) {
  const pid = projectId || (seed && seed.length > 8 && seed !== "pdf" ? seed : undefined);
  const kind = variant ?? paperVariantFor(template);
  const n = hash(seed);
  const cacheKey = pid ? `${pid}:${updatedAt || ""}` : "";

  const cachedInMemory = cacheKey ? previewMemoryCache.get(cacheKey) : null;
  const cachedLandscape = cacheKey ? previewLandscapeCache.get(cacheKey) || false : false;

  const [imageLandscape, setImageLandscape] = React.useState<boolean>(cachedLandscape);
  const landscape = kind === "beamer" || imageLandscape;
  const width = landscape ? LANDSCAPE_WIDTH[size] : PORTRAIT_WIDTH[size];
  const viewBox = landscape ? "0 0 210 132" : "0 0 148 210";

  const targetUrl =
    previewUrl ||
    (pid
      ? `/api/projects/preview?projectId=${encodeURIComponent(pid)}${
          updatedAt ? `&v=${encodeURIComponent(String(updatedAt))}` : ""
        }${template ? `&template=${encodeURIComponent(template)}` : ""}`
      : null);

  const [imageSrc, setImageSrc] = React.useState<string | null>(cachedInMemory || targetUrl);
  const [imageState, setImageState] = React.useState<"loading" | "loaded" | "error">(() => {
    if (cachedInMemory) return "loaded";
    return targetUrl ? "loading" : "error";
  });

  // User-side CacheStorage check & background revalidation
  React.useEffect(() => {
    if (!targetUrl || !cacheKey) {
      if (!targetUrl) setImageState("error");
      return;
    }

    if (previewMemoryCache.has(cacheKey)) {
      setImageSrc(previewMemoryCache.get(cacheKey)!);
      setImageState("loaded");
      return;
    }

    let isMounted = true;

    // Check persistent CacheStorage first (~1-2ms from local browser storage)
    if (typeof window !== "undefined" && "caches" in window) {
      caches.open(PREVIEW_CACHE_NAME).then(async (cache) => {
        try {
          const match = await cache.match(targetUrl);
          if (match && match.ok && isMounted) {
            const blob = await match.blob();
            const blobUrl = URL.createObjectURL(blob);
            previewMemoryCache.set(cacheKey, blobUrl);
            setImageSrc(blobUrl);
            setImageState("loaded");
            return;
          }
        } catch {}

        // Fetch from network and store in user-side cache
        try {
          const res = await fetch(targetUrl, { cache: "default" });
          if (!res.ok) {
            if (isMounted) setImageState("error");
            return;
          }
          const isFallback = res.headers.get("x-preview-fallback") === "true";
          const blob = await res.blob();
          const blobUrl = URL.createObjectURL(blob);
          if (isMounted) {
            previewMemoryCache.set(cacheKey, blobUrl);
            setImageSrc(blobUrl);
            setImageState("loaded");
          }
          if (!isFallback) {
            const cacheCopy = new Response(blob, {
              headers: { "Content-Type": res.headers.get("Content-Type") || "image/webp" },
            });
            await cache.put(targetUrl, cacheCopy);
          } else {
            // Re-check in background once TeX compiler finishes
            setTimeout(async () => {
              if (!isMounted) return;
              try {
                const refreshed = await fetch(targetUrl, { cache: "reload" });
                if (refreshed.ok && refreshed.headers.get("x-preview-fallback") !== "true") {
                  const rBlob = await refreshed.blob();
                  const rUrl = URL.createObjectURL(rBlob);
                  previewMemoryCache.set(cacheKey, rUrl);
                  if (isMounted) {
                    setImageSrc(rUrl);
                  }
                  await cache.put(targetUrl, new Response(rBlob, { headers: refreshed.headers }));
                }
              } catch {}
            }, 3500);
          }
        } catch {
          if (isMounted) setImageState("error");
        }
      });
    }

    return () => {
      isMounted = false;
    };
  }, [targetUrl, cacheKey]);

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    setImageState("loaded");
    if (cacheKey && imageSrc) {
      previewMemoryCache.set(cacheKey, imageSrc);
    }
    const img = e.currentTarget;
    if (img.naturalWidth && img.naturalHeight && img.naturalWidth > img.naturalHeight * 1.15) {
      setImageLandscape(true);
      if (cacheKey) previewLandscapeCache.set(cacheKey, true);
    }
  };

  return (
    <div
      aria-hidden="true"
      className={`relative shrink-0 p-3 text-ob-muted transition-all duration-300 ${className}`}
      style={{ width: width + 24 }}
    >
      {CORNERS.map((c) => (
        <svg
          key={c.className}
          viewBox="0 0 12 12"
          className={`absolute size-3 opacity-70 ${c.className}`}
          fill="none"
        >
          <path d={c.d} stroke="currentColor" strokeWidth={1} shapeRendering="crispEdges" />
        </svg>
      ))}
      <div className="relative">
        {kind === "thesis" && (
          <>
            <div className="ob-paper-under absolute inset-0 translate-x-1 translate-y-1" />
            <div className="ob-paper-under absolute inset-0 translate-x-0.5 translate-y-0.5" />
          </>
        )}
        <div
          className="ob-paper relative block w-full overflow-hidden border border-ob-line/30 shadow-sm"
          style={{ aspectRatio: landscape ? "210 / 132" : "148 / 210" }}
        >
          {imageSrc && imageState !== "error" && (
            <img
              src={imageSrc}
              alt=""
              loading="lazy"
              decoding="async"
              className={`absolute inset-0 h-full w-full object-contain bg-white transition-opacity duration-200 ${
                imageState === "loaded" ? "opacity-100" : "opacity-0"
              }`}
              onLoad={handleImageLoad}
              onError={() => setImageState("error")}
            />
          )}

          {/* Skeleton sketch: displayed underneath while loading, or as fallback if error / no project */}
          {imageState !== "loaded" && (
            <svg
              viewBox={viewBox}
              className={`relative block h-auto w-full transition-opacity duration-200 ${
                imageState === "loading" ? "opacity-40 animate-pulse" : "opacity-100"
              }`}
            >
              {kind === "article" && <Article n={n} />}
              {kind === "ieee" && <Ieee n={n} />}
              {kind === "beamer" && <Beamer n={n} />}
              {kind === "thesis" && <Thesis n={n} />}
              {kind === "assignment" && <Assignment n={n} />}
              {kind === "report" && <Report n={n} />}
            </svg>
          )}
        </div>
      </div>
    </div>
  );
}
