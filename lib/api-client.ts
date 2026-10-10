/**
 * lib/api-client.ts — Authenticated API Client Helper for OverBranch
 * =================================================================
 * Automatically attaches Better-Auth Bearer tokens, user identity headers,
 * and guest HMAC tokens to all backend API calls.
 */

import { authClient } from "./auth-client";

/**
 * Returns authorization headers including Bearer token, user ID, and guest token.
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};

  // 1. Better-Auth active session
  try {
    const sessionRes = await authClient.getSession();
    const token = sessionRes?.data?.session?.token;
    const userId = sessionRes?.data?.user?.id;

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    if (userId) {
      headers["X-User-Id"] = userId;
    }
  } catch (err) {
    // Non-fatal if session lookup fails
  }

  // 2. Guest token — ONLY when there is no session to speak for us.
  //
  // A guest token is minted on any signed-out visit and nothing clears it at
  // sign-in, so it outlives the anonymous session that created it. Sending it
  // next to a real Bearer token gave the backend two identities for one
  // request, and whenever the session was not accepted it quietly used the
  // other one: a signed-in collaborator became an anonymous visitor and was
  // told they had no access to a project they can edit. The backend now
  // refuses that downgrade; not offering a second identity in the first place
  // is the other half of the fix.
  //
  // Guest flows are unaffected — they have no session — and guest migration
  // passes its token in the request body, not this header.
  if (!headers["Authorization"] && typeof window !== "undefined") {
    let guestToken = localStorage.getItem("ob_guest_token");
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
