/**
 * app/api/projects/export-all/route.ts — same-origin proxy for "download every project as .zip".
 *
 * Same reason as get-file/route.ts: the Python backend lives on a different origin, so a plain
 * `<a download>` at the backend URL carries no Better-Auth cookie and the backend sees an
 * anonymous request. This route runs on the app's origin, verifies the session server-side,
 * and streams GET /api/projects/export-all.zip (one top-level folder per project) from the backend with the session token
 * attached as a Bearer (or the guest token as x-guest-token). The backend does the real
 * own/member/guest project listing and flushes each live collab room before zipping.
 *
 * Usage: GET /api/projects/export-all
 */
import { NextRequest, NextResponse } from "next/server";
import { headers as nextHeaders } from "next/headers";

import { auth } from "@/lib/auth";

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

/** The Better-Auth session token, same shape the backend expects as a Bearer. */
function sessionTokenFromCookies(req: NextRequest): string | null {
  for (const name of SESSION_COOKIE_CANDIDATES) {
    const v = req.cookies.get(name)?.value;
    if (v) return decodeURIComponent(v).split(".")[0] || null;
  }
  return null;
}

export async function GET(req: NextRequest) {
  // 1. Server-side identity: a signed-in user, or a guest token (the backend verifies its HMAC).
  let userId: string | null = null;
  try {
    const session = await auth.api.getSession({ headers: await nextHeaders() });
    userId = session?.user?.id || null;
  } catch (err) {
    console.warn("[export-all proxy] session lookup failed:", err);
  }
  const guestToken = req.cookies.get("ob_guest_token")?.value || "";
  if (!userId && !guestToken) {
    return NextResponse.json({ detail: "Please sign in to download your projects." }, { status: 401 });
  }

  // 2. Forward. Bearer for a signed-in user; otherwise only the guest identity (never both).
  const fwd = new Headers();
  const token = sessionTokenFromCookies(req);
  if (userId && token) {
    fwd.set("authorization", `Bearer ${token}`);
  } else if (guestToken) {
    fwd.set("x-guest-token", guestToken);
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/api/projects/export-all.zip`, { headers: fwd, cache: "no-store" });
  } catch (err: any) {
    return NextResponse.json({ detail: `Upstream fetch failed: ${err?.message || err}` }, { status: 502 });
  }

  if (!upstream.ok) {
    // Pass the backend's own status/detail through (404 when there is nothing to export).
    const text = await upstream.text().catch(() => "");
    try {
      return NextResponse.json(JSON.parse(text), { status: upstream.status });
    } catch {
      return new NextResponse(text || upstream.statusText, { status: upstream.status });
    }
  }

  // 3. Stream the archive through, keeping the backend's filename and type.
  const headers = new Headers();
  headers.set("content-type", upstream.headers.get("content-type") || "application/zip");
  const disposition = upstream.headers.get("content-disposition");
  headers.set("content-disposition", disposition || 'attachment; filename="overbranch-projects.zip"');
  const len = upstream.headers.get("content-length");
  if (len) headers.set("content-length", len);
  headers.set("cache-control", "private, no-store");
  headers.set("x-content-type-options", "nosniff");
  return new NextResponse(upstream.body, { status: 200, headers });
}
