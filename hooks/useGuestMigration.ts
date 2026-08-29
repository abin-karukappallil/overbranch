"use client";

import { useEffect, useRef } from "react";
import { authClient } from "@/lib/auth-client";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

export function useGuestMigration() {
  const { data: session, isPending } = authClient.useSession();
  const hasAttemptedRef = useRef(false);
  const router = useRouter();

  useEffect(() => {
    if (isPending || !session?.user?.id || hasAttemptedRef.current) return;

    // Check localStorage and document.cookie for guest token
    let token = typeof window !== "undefined" ? localStorage.getItem("ob_guest_token") : null;
    if (!token && typeof document !== "undefined") {
      const match = document.cookie.match(/ob_guest_token=([^;]+)/);
      if (match) token = match[1];
    }

    const performMigration = async () => {
      hasAttemptedRef.current = true;

      try {
        // If we don't have an explicit token in client storage, probe backend session endpoint
        // which has access to the HttpOnly cookie
        if (!token) {
          try {
            const sessionRes = await fetch(`${BACKEND_URL}/api/guest/session`, {
              credentials: "include",
            });
            if (sessionRes.ok) {
              const sessionData = await sessionRes.json();
              if (sessionData?.token) {
                token = sessionData.token;
              }
            }
          } catch {
            // Ignore probe failure
          }
        }

        // Call migration endpoint with user_id and guest_token
        const res = await fetch(`${BACKEND_URL}/api/guest/migrate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            user_id: session.user.id,
            guest_token: token || undefined,
          }),
        });

        if (!res.ok) return;

        const data = await res.json();
        if (data.success && data.migrated_count > 0) {
          toast.success(
            data.message || `Your guest project has been permanently saved to your account!`,
            {
              duration: 7000,
              icon: "",
            }
          );

          // Clear client-side token storage
          if (typeof window !== "undefined") {
            localStorage.removeItem("ob_guest_token");
          }
          if (typeof document !== "undefined") {
            document.cookie = "ob_guest_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
          }

          // Trigger page refresh so projects and editor permissions update
          router.refresh();
        }
      } catch (err) {
        console.warn("Guest migration error:", err);
      }
    };

    performMigration();
  }, [session, isPending, router]);
}
