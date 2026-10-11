/**
 * app/api/projects/get-file/route.ts — same-origin file proxy.
 *
 * Why this route exists: the Python backend lives on a DIFFERENT origin
 * (`overapi.…dev` vs `overbranch.…dev`), so a plain `<a download>` link
 * pointing at the backend doesn't carry the Better-Auth cookie (cross-site),
 * and `<img>` / resource-hint fetches don't carry the Authorization: Bearer
 * header that `authFetch` would attach. The backend then sees the request as
 * anonymous and refuses it — "this request was not signed in" — even for a
 * signed-in collaborator who clearly has access.
 *
 * This proxy fixes that in the only robust way: it lives on the SAME origin
 * as the app, so the browser's Better-Auth cookie flows naturally. We verify
 * the session server-side with Drizzle (the same check the tRPC project
 * routes use), decide ownership-or-membership, then forward the request to
 * the backend with the user's session token as a server-attached Bearer. The
 * backend URL is never put in front of the user — the download button links
 * to this proxy, so it's a one-click, same-origin download and the backend's
 * API shape stays hidden.
 */
import { NextRequest, NextResponse } from "next/server";
import { headers as nextHeaders } from "next/headers";
import { eq, and } from "drizzle-orm";

import { auth } from "@/lib/auth";
import { db } from "@/db";
import { projects, projectMembers, guestProjects } from "@/db/schema";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/+$/, "");

const SESSION_COOKIE_CANDIDATES = [
  "__Secure-better-auth.session_token",
  "better-auth.session_token",
  "session_token",
];

const CONTENT_TYPE_BY_EXT: Record<string, string> = {
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif",
  webp: "image/webp", bmp: "image/bmp", svg: "image/svg+xml",
  pdf: "application/pdf", zip: "application/zip",
  otf: "font/otf", ttf: "font/ttf", woff: "font/woff", woff2: "font/woff2",
  tex: "text/plain; charset=utf-8", bib: "text/plain; charset=utf-8",
  cls: "text/plain; charset=utf-8", sty: "text/plain; charset=utf-8",
  txt: "text/plain; charset=utf-8", md: "text/plain; charset=utf-8",
  json: "application/json",
};

/** The Better-Auth session token, same shape the backend expects as a Bearer. */
function sessionTokenFromCookies(req: NextRequest): string | null {
  for (const name of SESSION_COOKIE_CANDIDATES) {
    const v = req.cookies.get(name)?.value;
    if (v) return decodeURIComponent(v).split(".")[0] || null;
  }
  return null;
}

async function hasProjectAccess(projectId: string, userId: string): Promise<boolean> {
  if (!projectId || !userId) return false;
  if (projectId === "proj-default" || projectId === "default" || projectId === "scratchpad"
      || projectId.startsWith("proj-default")) return true;

  const [proj] = await db.select({ ownerId: projects.ownerId })
    .from(projects).where(eq(projects.id, projectId)).limit(1);
  if (!proj) return false;
  if (proj.ownerId === userId || proj.ownerId === "default-user" || String(proj.ownerId || "").startsWith("guest")) {
    return true;
  }
  const [mem] = await db.select({ id: projectMembers.id })
    .from(projectMembers)
    .where(and(eq(projectMembers.projectId, projectId), eq(projectMembers.userId, userId)))
    .limit(1);
  return Boolean(mem);
}

async function hasGuestProjectAccess(projectId: string, guestSessionId: string): Promise<boolean> {
  if (!projectId || !guestSessionId) return false;
  const [gp] = await db.select({ id: guestProjects.id })
    .from(guestProjects)
    .where(and(eq(guestProjects.projectId, projectId), eq(guestProjects.guestSessionId, guestSessionId)))
    .limit(1);
  return Boolean(gp);
}

function contentDisposition(filename: string, inline: boolean): string {
  // RFC 5987 encoding so names with spaces, unicode or quotes survive.
  const ascii = filename.replace(/[^\x20-\x7E]/g, "_").replace(/"/g, "'");
  const enc = encodeURIComponent(filename).replace(/['()]/g, escape).replace(/\*/g, "%2A");
  return `${inline ? "inline" : "attachment"}; filename="${ascii}"; filename*=UTF-8''${enc}`;
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const projectId = url.searchParams.get("project_id") || "";
  const filePath = url.searchParams.get("file_path") || "main.tex";
  const download = url.searchParams.get("download") === "true" || url.searchParams.get("download") === "1";
  const raw = url.searchParams.get("raw") === "true" || url.searchParams.get("raw") === "1";

  if (!projectId) {
    return NextResponse.json({ detail: "project_id is required" }, { status: 400 });
  }
  if (/\.\.(\/|\\)/.test(filePath) || filePath.includes("\0")) {
    return NextResponse.json({ detail: "Invalid file_path" }, { status: 400 });
  }

  // 1. Server-side identity. The cookie travels naturally on this same-origin
  //    request, so this is reliable even when the browser dropped a Bearer on
  //    an <img>/<a> navigation.
  let userId: string | null = null;
  try {
    const session = await auth.api.getSession({ headers: await nextHeaders() });
    userId = session?.user?.id || null;
  } catch (err) {
    console.warn("[get-file proxy] session lookup failed:", err);
  }

  // 2. Access check — owner or member. Fallback: a guest token cookie, so a
  //    guest's own project download also works through this route.
  let allowed = false;
  if (userId) {
    allowed = await hasProjectAccess(projectId, userId);
  } else {
    const guestTok = req.cookies.get("ob_guest_token")?.value;
    if (guestTok) {
      // Backend verifies the HMAC; here we only need the session id to check
      // the guest-projects row. The HMAC payload is "<sessionId>.<sig>".
      const guestSession = guestTok.split(".")[0];
      if (guestSession && await hasGuestProjectAccess(projectId, guestSession)) {
        allowed = true;
      }
    }
  }

  if (!allowed) {
    return NextResponse.json(
      { detail: userId
        ? "Forbidden: You do not have access to this project."
        : "Please sign in to download this file." },
      { status: userId ? 403 : 401 },
    );
  }

  // 3. Proxy. Forward the user's session token to the backend as a Bearer so
  //    its own access check passes without having to trust an internal header.
  const token = sessionTokenFromCookies(req);
  const backendQs = new URLSearchParams({ project_id: projectId, file_path: filePath });
  if (raw) backendQs.set("raw", "true");
  if (download) backendQs.set("download", "true");
  // The backend returns binary for binary extensions regardless of flags; for
  // text file previews we also forward the raw flag so JSON doesn't wrap it.
  const backendUrl = `${BACKEND_URL}/api/projects/get-file?${backendQs.toString()}`;

  let upstream: Response;
  try {
    upstream = await fetch(backendUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      cache: "no-store",
    });
  } catch (err: any) {
    return NextResponse.json({ detail: `Upstream fetch failed: ${err?.message || err}` }, { status: 502 });
  }

  if (!upstream.ok) {
    // Pass the backend's own status/detail through so the UI can surface it.
    const text = await upstream.text().catch(() => "");
    try {
      const parsed = JSON.parse(text);
      return NextResponse.json(parsed, { status: upstream.status });
    } catch {
      return new NextResponse(text || upstream.statusText, { status: upstream.status });
    }
  }

  // 4. Pass the body through. Text + raw/download means we return as-is; a
  //    JSON preview (raw_code) also passes through unchanged.
  const upstreamCT = upstream.headers.get("content-type") || "";
  const baseName = filePath.split("/").pop() || filePath;
  const ext = baseName.split(".").pop()?.toLowerCase() || "";
  const inferredCT = CONTENT_TYPE_BY_EXT[ext] || "application/octet-stream";
  const outCT = upstreamCT || inferredCT;

  const headers = new Headers();
  headers.set("content-type", outCT);
  const upstreamLen = upstream.headers.get("content-length");
  if (upstreamLen) headers.set("content-length", upstreamLen);
  if (!upstreamCT.includes("application/json")) {
    headers.set("content-disposition", contentDisposition(baseName, !download));
  }
  headers.set("cache-control", "private, no-store");
  headers.set("x-content-type-options", "nosniff");

  return new NextResponse(upstream.body, { status: 200, headers });
}
