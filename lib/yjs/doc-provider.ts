import * as Y from "yjs";
import { getSupabaseClient } from "@/lib/supabase-client";
import type { RealtimeChannel } from "@supabase/supabase-js";

/**
 * Yjs ↔ Supabase Realtime Broadcast provider (spec section 1).
 *
 * - Creates a Y.Doc per document
 * - Subscribes to Broadcast channel `document:{documentId}`
 * - On local Yjs update → base64-encode delta → broadcast
 * - On remote broadcast → decode → Y.applyUpdate
 * - Debounced snapshot persistence (2-5s inactivity or tab blur/unmount)
 */
export class SupabaseYjsProvider {
  doc: Y.Doc;
  documentId: string;
  projectId: string;
  channel: RealtimeChannel | null = null;
  private saveCallback: ((state: string) => Promise<void>) | null = null;
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private isDestroyed = false;
  private pendingUpdates: Uint8Array[] = [];
  private isConnected = false;

  constructor(
    documentId: string,
    projectId: string,
    options?: {
      onSave?: (base64State: string) => Promise<void>;
      debounceMs?: number;
    }
  ) {
    this.doc = new Y.Doc();
    this.documentId = documentId;
    this.projectId = projectId;
    this.saveCallback = options?.onSave || null;

    const debounceMs = options?.debounceMs ?? 3000;

    // Listen for local Yjs updates → broadcast to channel
    this.doc.on("update", (update: Uint8Array, origin: unknown) => {
      // Don't re-broadcast remote updates (would cause loops)
      if (origin === "remote") return;

      this.broadcastUpdate(update);
      this.scheduleSave(debounceMs);
    });

    // Save on tab blur/unmount
    if (typeof window !== "undefined") {
      window.addEventListener("beforeunload", this.handleUnload);
      document.addEventListener("visibilitychange", this.handleVisibilityChange);
    }
  }

  /**
   * Connect to the Supabase Realtime Broadcast channel and start syncing.
   */
  async connect() {
    if (this.isDestroyed) return;

    const supabase = getSupabaseClient();
    const channelName = `document:${this.documentId}`;

    this.channel = supabase.channel(channelName, {
      config: {
        broadcast: { self: false }, // Don't echo own messages
      },
    });

    // Listen for remote Yjs updates
    this.channel.on("broadcast", { event: "document.change" }, (payload) => {
      if (this.isDestroyed) return;

      try {
        const base64Update = payload.payload?.update;
        if (!base64Update) return;

        const update = base64ToUint8Array(base64Update);
        Y.applyUpdate(this.doc, update, "remote");
      } catch (err) {
        console.warn("[YjsProvider] Failed to apply remote update:", err);
      }
    });

    await this.channel.subscribe((status) => {
      this.isConnected = status === "SUBSCRIBED";

      if (this.isConnected) {
        // Flush any updates that accumulated while disconnected
        this.flushPendingUpdates();
      }
    });
  }

  /**
   * Load the initial Yjs state from a base64-encoded snapshot.
   */
  loadSnapshot(base64Snapshot: string) {
    try {
      const snapshot = base64ToUint8Array(base64Snapshot);
      Y.applyUpdate(this.doc, snapshot, "remote");
    } catch (err) {
      console.warn("[YjsProvider] Failed to load snapshot:", err);
    }
  }

  /**
   * Get the current Y.Text field for the document content.
   */
  getText(fieldName: string = "content"): Y.Text {
    return this.doc.getText(fieldName);
  }

  /**
   * Get the full Yjs state as a base64-encoded string for persistence.
   */
  getStateAsBase64(): string {
    const state = Y.encodeStateAsUpdate(this.doc);
    return uint8ArrayToBase64(state);
  }

  /**
   * Broadcast a Yjs update delta to the channel.
   */
  private broadcastUpdate(update: Uint8Array) {
    if (!this.channel || !this.isConnected) {
      // Queue updates while disconnected
      this.pendingUpdates.push(update);
      return;
    }

    const base64Update = uint8ArrayToBase64(update);

    this.channel.send({
      type: "broadcast",
      event: "document.change",
      payload: { update: base64Update },
    });
  }

  /**
   * Flush queued updates that accumulated while offline.
   */
  private flushPendingUpdates() {
    if (this.pendingUpdates.length === 0) return;

    // Merge all pending updates into one
    const merged = Y.mergeUpdates(this.pendingUpdates);
    this.pendingUpdates = [];

    const base64Update = uint8ArrayToBase64(merged);

    this.channel?.send({
      type: "broadcast",
      event: "document.change",
      payload: { update: base64Update },
    });
  }

  /**
   * Schedule a debounced save of the current Yjs state.
   */
  private scheduleSave(debounceMs: number) {
    if (this.saveTimer) clearTimeout(this.saveTimer);

    this.saveTimer = setTimeout(() => {
      this.save();
    }, debounceMs);
  }

  /**
   * Persist the current Yjs state immediately.
   */
  async save() {
    if (!this.saveCallback || this.isDestroyed) return;

    try {
      const state = this.getStateAsBase64();
      await this.saveCallback(state);
    } catch (err) {
      console.error("[YjsProvider] Save failed:", err);
    }
  }

  private handleUnload = () => {
    this.save();
  };

  private handleVisibilityChange = () => {
    if (document.visibilityState === "hidden") {
      this.save();
    }
  };

  /**
   * Clean up the provider — unsubscribe from the channel and destroy the Y.Doc.
   */
  async destroy() {
    this.isDestroyed = true;

    // Save before destroying
    await this.save();

    if (this.saveTimer) clearTimeout(this.saveTimer);

    if (typeof window !== "undefined") {
      window.removeEventListener("beforeunload", this.handleUnload);
      document.removeEventListener("visibilitychange", this.handleVisibilityChange);
    }

    if (this.channel) {
      const supabase = getSupabaseClient();
      await supabase.removeChannel(this.channel);
      this.channel = null;
    }

    this.doc.destroy();
  }
}

// ─── Base64 ↔ Uint8Array helpers ───────────────────────────────────

function uint8ArrayToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToUint8Array(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}
