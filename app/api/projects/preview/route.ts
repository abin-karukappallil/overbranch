/**
 * app/api/projects/preview/route.ts — same-origin project compiled PDF preview proxy.
 *
 * Provides a same-origin image endpoint for project compiled PDF first-page previews:
 * 1. Checks user or guest session from cookies.
 * 2. Verifies project ownership / membership via Drizzle.
 * 3. Proxies the request to the Python backend with the session token attached.
 * 4. Streams the first-page image or forwards its revalidation status.
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

function sessionTokenFromCookies(req: NextRequest): string | null {
  for (const name of SESSION_COOKIE_CANDIDATES) {
    const v = req.cookies.get(name)?.value;
    if (v) return decodeURIComponent(v).split(".")[0] || null;
  }
  return null;
}

async function hasProjectAccess(projectId: string, userId: string): Promise<boolean> {
  if (!projectId || !userId) return false;
  if (
    projectId === "proj-default" ||
    projectId === "default" ||
    projectId === "scratchpad" ||
    projectId.startsWith("proj-default")
  ) {
    return true;
  }

  const [proj] = await db
    .select({ ownerId: projects.ownerId })
    .from(projects)
    .where(eq(projects.id, projectId))
    .limit(1);
  if (!proj) return false;
  if (
    proj.ownerId === userId ||
    proj.ownerId === "default-user" ||
    String(proj.ownerId || "").startsWith("guest")
  ) {
    return true;
  }
  const [mem] = await db
    .select({ id: projectMembers.id })
    .from(projectMembers)
    .where(and(eq(projectMembers.projectId, projectId), eq(projectMembers.userId, userId)))
    .limit(1);
  return Boolean(mem);
}

async function hasGuestProjectAccess(projectId: string, guestSessionId: string): Promise<boolean> {
  if (!projectId || !guestSessionId) return false;
  const [gp] = await db
    .select({ id: guestProjects.id })
    .from(guestProjects)
    .where(and(eq(guestProjects.projectId, projectId), eq(guestProjects.guestSessionId, guestSessionId)))
    .limit(1);
  return Boolean(gp);
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const projectId = url.searchParams.get("projectId") || url.searchParams.get("project_id") || "";
  const refresh = url.searchParams.get("refresh") === "true";
  const wait = url.searchParams.get("wait") === "true";
  const template = url.searchParams.get("template") || "";

  if (!projectId) {
    return NextResponse.json({ detail: "projectId is required" }, { status: 400 });
  }

  // 1. Session check
  let userId: string | null = null;
  try {
    const session = await auth.api.getSession({ headers: await nextHeaders() });
    userId = session?.user?.id || null;
  } catch (err) {
    console.warn("[preview proxy] session lookup failed:", err);
  }

  // 2. Project access check
  let allowed = false;
  const guestTok = req.cookies.get("ob_guest_token")?.value;
  if (userId) {
    allowed = await hasProjectAccess(projectId, userId);
  } else if (guestTok) {
    const guestSession = guestTok.split(".")[0];
    if (guestSession && (await hasGuestProjectAccess(projectId, guestSession))) {
      allowed = true;
    }
  }

  if (!allowed) {
    return NextResponse.json(
      { detail: userId ? "Forbidden: Access denied to this project" : "Please sign in to view this preview." },
      { status: userId ? 403 : 401 }
    );
  }

  // 3. Forward to backend
  const token = sessionTokenFromCookies(req);
  const forwardHeaders: Record<string, string> = {};
  if (token) forwardHeaders["Authorization"] = `Bearer ${token}`;
  if (guestTok) forwardHeaders["X-Guest-Token"] = guestTok;
  const rawCookie = req.headers.get("cookie");
  if (rawCookie) forwardHeaders["Cookie"] = rawCookie;
  const validator = req.headers.get("if-none-match");
  if (validator) forwardHeaders["If-None-Match"] = validator;

  const backendQs = new URLSearchParams({ project_id: projectId });
  if (refresh) backendQs.set("refresh", "true");
  if (wait) backendQs.set("wait", "true");
  if (template) backendQs.set("template", template);
  const backendUrl = `${BACKEND_URL}/api/projects/preview?${backendQs.toString()}`;

  let upstream: Response;
  try {
    upstream = await fetch(backendUrl, {
      headers: forwardHeaders,
      cache: "no-store",
      signal: req.signal,
    });
  } catch (err: any) {
    return NextResponse.json(
      { detail: `Upstream preview fetch failed: ${err?.message || err}` },
      { status: 502 }
    );
  }

  if (!upstream.ok && upstream.status !== 304) {
    const text = await upstream.text().catch(() => "");
    try {
      const parsed = JSON.parse(text);
      return NextResponse.json(parsed, { status: upstream.status, headers: { "Cache-Control": "no-store" } });
    } catch {
      return new NextResponse(text || upstream.statusText, { status: upstream.status, headers: { "Cache-Control": "no-store" } });
    }
  }

  const headers = new Headers({
    "Cache-Control": "no-store",
    "Vary": "Cookie",
    "X-Content-Type-Options": "nosniff",
  });
  for (const name of ["cache-control", "content-type", "etag", "x-preview-fallback", "x-preview-pending"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }

  return new NextResponse(upstream.body, { status: upstream.status, headers });
}

