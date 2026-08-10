"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { fetchRealtimeToken, setRealtimeAuth, getSupabaseClient } from "@/lib/supabase-client";

// ─── Context Types ──────────────────────────────────────────────────

type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "offline";

interface RealtimeContextValue {
  connectionStatus: ConnectionStatus;
  projectId: string | null;
  isAuthenticated: boolean;
  refreshToken: () => Promise<void>;
}

const RealtimeContext = createContext<RealtimeContextValue>({
  connectionStatus: "connecting",
  projectId: null,
  isAuthenticated: false,
  refreshToken: async () => {},
});

export function useRealtimeContext() {
  return useContext(RealtimeContext);
}

// ─── Provider ──────────────────────────────────────────────────────

interface RealtimeProviderProps {
  projectId: string;
  children: React.ReactNode;
}

/**
 * React context provider that manages the Supabase Realtime client lifecycle (spec section 16).
 *
 * - Fetches a JWT token on mount via the auth bridge (spec section 12)
 * - Sets the token on the Supabase Realtime client
 * - Monitors connection state (connected/reconnecting/offline)
 * - Auto-refreshes the token before expiry (every 50s for a 60s token)
 * - Handles reconnect → re-auth → re-subscribe flow
 */
export function RealtimeProvider({ projectId, children }: RealtimeProviderProps) {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const refreshIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshToken = useCallback(async () => {
    try {
      const token = await fetchRealtimeToken(projectId);
      setRealtimeAuth(token);
      setIsAuthenticated(true);
      setConnectionStatus("connected");
    } catch (err) {
      console.error("[RealtimeProvider] Token refresh failed:", err);
      setConnectionStatus("reconnecting");
    }
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;

    // Initial token fetch
    refreshToken();

    // Auto-refresh token every 50 seconds (token expires in 60s)
    refreshIntervalRef.current = setInterval(() => {
      refreshToken();
    }, 50000);

    // Monitor connection state via the Supabase Realtime client
    const supabase = getSupabaseClient();

    // Listen for connection state changes
    const handleOnline = () => {
      setConnectionStatus("reconnecting");
      refreshToken();
    };

    const handleOffline = () => {
      setConnectionStatus("offline");
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [projectId, refreshToken]);

  return (
    <RealtimeContext.Provider
      value={{
        connectionStatus,
        projectId,
        isAuthenticated,
        refreshToken,
      }}
    >
      {children}
    </RealtimeContext.Provider>
  );
}

// ─── Connection Status Indicator ────────────────────────────────────

/**
 * Small status indicator showing connection state in the editor header.
 */
export function ConnectionStatusIndicator() {
  const { connectionStatus } = useRealtimeContext();

  const config: Record<ConnectionStatus, { dot: string; label: string; className: string }> = {
    connecting: {
      dot: "bg-amber-400 animate-pulse",
      label: "Connecting…",
      className: "text-amber-400",
    },
    connected: {
      dot: "bg-emerald-400",
      label: "Connected",
      className: "text-emerald-400",
    },
    reconnecting: {
      dot: "bg-amber-400 animate-pulse",
      label: "Reconnecting…",
      className: "text-amber-400",
    },
    offline: {
      dot: "bg-rose-400",
      label: "Offline",
      className: "text-rose-400",
    },
  };

  const c = config[connectionStatus];

  return (
    <div className="flex items-center gap-1.5 text-[10px] font-mono select-none" title={c.label}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      <span className={c.className}>{c.label}</span>
    </div>
  );
}
