/**
 * lib/api-client.ts — Authenticated API Client Helper for OverBranch
 * =================================================================
 * Automatically attaches Better-Auth Bearer tokens, user identity headers,
 * and guest HMAC tokens to all backend API calls.
 */

import { authClient } from "./auth-client";

// Last good session, kept for the life of this tab. In production the app and the API are
// different sites, so the Better Auth cookie never reaches the backend: the Bearer token is the
// ONLY user credential. One getSession() that fails, times out or is rate limited (429) used to
// send the request with no Bearer, and a leftover X-Guest-Token then made the backend treat a
// signed-in user as `guest_<sid>`. Reusing the cached token, and never offering a guest identity
// once a signed-in user has been seen, closes that downgrade.
let cachedToken: string | null = null;
let cachedUserId: string | null = null;
let sawSignedInUser = false;

/** Forgets the cached session (call on an explicit sign-out). */
export function clearCachedSession(): void {
  cachedToken = null;
  cachedUserId = null;
  sawSignedInUser = false;
}

/**
 * Asks Better Auth for the current session, bypassing nothing but remembering the result.
 * Never throws; returns the token in use (fresh, else cached) or null.
 */
export async function refreshSession(): Promise<string | null> {
  try {
    const sessionRes = await authClient.getSession();
    const token = sessionRes?.data?.session?.token;
    const userId = sessionRes?.data?.user?.id;
    if (token) {
      cachedToken = token;
      sawSignedInUser = true;
      if (userId) cachedUserId = userId;
    } else if (sawSignedInUser && sessionRes && !sessionRes.error && sessionRes.data === null) {
      // A clean "no session" answer (no error, no throw) is a real sign-out, unlike a 429, a
      // timeout or a network error, which all arrive as an error or an exception.
      clearCachedSession();
    }
  } catch {
    // Non-fatal: fall back to the cached session below.
  }
  return cachedToken;
}

/**
 * Returns authorization headers including Bearer token, user ID, and guest token.
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};

  // 1. Better-Auth active session, falling back to the last good one.
  await refreshSession();
  if (cachedToken) headers["Authorization"] = `Bearer ${cachedToken}`;
  if (cachedUserId) headers["X-User-Id"] = cachedUserId;

  // 2. Guest token: only when this tab has never seen a signed-in user. A guest token is minted
  // on any signed-out visit and nothing clears it at sign-in, so it outlives the anonymous
  // session; sending it next to (or instead of) a real session gave the backend a second
  // identity to fall back to. Guest flows are unaffected (no session was ever seen), and guest
  // migration passes its token in the request body, not this header.
  if (!headers["Authorization"] && !sawSignedInUser && typeof window !== "undefined") {
    let guestToken: string | null = null;
    try {
      guestToken = localStorage.getItem("ob_guest_token");
    } catch {
      /* storage blocked */
    }
    if (!guestToken && typeof document !== "undefined") {
      const match = document.cookie.match(/ob_guest_token=([^;]+)/);
      if (match) guestToken = match[1];
    }
    if (guestToken) {
      headers["X-Guest-Token"] = guestToken;
    }
  }

  return headers;
}

/**
 * Enhanced fetch that automatically attaches Authorization Bearer tokens,
 * credentials, and custom headers for OverBranch backend APIs.
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const authHeaders = await getAuthHeaders();
  const mergedHeaders = new Headers(init?.headers || {});

  for (const [key, value] of Object.entries(authHeaders)) {
    if (!mergedHeaders.has(key)) {
      mergedHeaders.set(key, value);
    }
  }

  return fetch(input, {
    ...init,
    headers: mergedHeaders,
    credentials: init?.credentials || "include",
  });
}
