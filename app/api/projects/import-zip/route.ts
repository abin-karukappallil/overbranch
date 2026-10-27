/**
 * app/api/projects/import-zip/route.ts — same-origin proxy for "import project from ZIP".
 *
 * Same reason as get-file/route.ts: the Python backend lives on a different origin, so the
 * Better-Auth cookie never reaches it. This route runs on the app's origin, verifies the
 * session server-side, and forwards the raw multipart body to the backend with the session
 * token attached as a Bearer. The backend does the real validation (zip-slip, bombs, caps);
 * this layer only authenticates and relays, returning the backend's JSON + status verbatim.
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

export async function POST(req: NextRequest) {
  // 1. Server-side identity: a signed-in user, or a guest token (the backend verifies its HMAC).
  let userId: string | null = null;
  try {
    const session = await auth.api.getSession({ headers: await nextHeaders() });
    userId = session?.user?.id || null;
  } catch (err) {
    console.warn("[import-zip proxy] session lookup failed:", err);
  }
  const guestToken =
    req.cookies.get("ob_guest_token")?.value || req.headers.get("x-guest-token") || "";
  if (!userId && !guestToken) {
    return NextResponse.json({ detail: "Please sign in to import a project." }, { status: 401 });
  }

  const contentType = req.headers.get("content-type") || "";
  if (!contentType.toLowerCase().startsWith("multipart/form-data")) {
    return NextResponse.json({ detail: "Expected a multipart/form-data upload." }, { status: 400 });
  }

  // 2. Forward. Bearer for a signed-in user; otherwise only the guest identity, never both
  //    (two identities on one request is what the backend refuses).
  const fwd = new Headers();
  fwd.set("content-type", contentType);
  const len = req.headers.get("content-length");
  if (len) fwd.set("content-length", len);
  const cookie = req.headers.get("cookie");
  if (cookie) fwd.set("cookie", cookie);
  const token = sessionTokenFromCookies(req);
  if (userId && token) {
    fwd.set("authorization", `Bearer ${token}`);
  } else if (guestToken) {
    fwd.set("x-guest-token", guestToken);
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/api/projects/import-zip`, {
      method: "POST",
      headers: fwd,
      body: req.body,
      // Streaming a request body requires half-duplex mode in Node's fetch.
      // @ts-expect-error `duplex` is not in the DOM RequestInit typings yet.
      duplex: "half",
      cache: "no-store",
    });
  } catch (err: any) {
    return NextResponse.json({ detail: `Upstream fetch failed: ${err?.message || err}` }, { status: 502 });
  }

  // 3. Relay JSON + status verbatim (non-JSON error bodies are wrapped so the client always gets JSON).
  const text = await upstream.text().catch(() => "");
  try {
    return NextResponse.json(JSON.parse(text), { status: upstream.status });
  } catch {
    return NextResponse.json(
      { detail: text || upstream.statusText || "Import failed" },
      { status: upstream.ok ? 502 : upstream.status },
    );
  }
}
