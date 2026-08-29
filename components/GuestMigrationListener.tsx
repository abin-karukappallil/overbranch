"use client";

import { useGuestMigration } from "@/hooks/useGuestMigration";

export function GuestMigrationListener() {
  useGuestMigration();
  return null;
}
