"use client";

import { createClient, SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY || "";

let supabaseInstance: SupabaseClient | null = null;

/**
 * Browser-side Supabase client for Realtime subscriptions.
 * Uses the anon key initially. After the JWT token exchange (section 12),
 * call `setRealtimeAuth(token)` to authenticate channels.
 *
 * Singleton — reused across the app to share a single Realtime connection.
 */
export function getSupabaseClient(): SupabaseClient {
  if (supabaseInstance) return supabaseInstance;

  supabaseInstance = createClient(supabaseUrl, supabaseAnonKey, {
    realtime: {
      params: {
        eventsPerSecond: 20,
      },
    },
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });

  return supabaseInstance;
}

/**
 * Set the Realtime auth token after the JWT bridge returns a token.
 * This authenticates the Supabase Realtime connection for channel authorization.
 */
export function setRealtimeAuth(token: string) {
  const client = getSupabaseClient();
  client.realtime.setAuth(token);
}

/**
 * Fetch a short-lived Supabase-compatible JWT from the auth bridge.
 * Validates the Better Auth session server-side and mints a JWT
 * with the user's project membership claims.
 */
export async function fetchRealtimeToken(projectId: string): Promise<string> {
  const res = await fetch(`/api/realtime/token?projectId=${encodeURIComponent(projectId)}`, {
    credentials: "include", // send Better Auth session cookies
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Token fetch failed" }));
    throw new Error(err.error || "Failed to fetch realtime token");
  }

  const { token } = await res.json();
  return token;
}
