"use client";

/**
 * lib/collab/useCollaboration.ts — The collaboration session for one project
 * ==========================================================================
 * Owns, for the lifetime of an open project:
 *
 *   Y.Doc  ──  WebsocketProvider (room = projectId)  ──  /ws/collab/{projectId}
 *     │
 *     └── Y.Text "file:<path>"  ──  MonacoYBinding  ──  the shared Monaco model
 *
 * One room per project, one Y.Text per file: switching files re-binds inside
 * the same socket and the same presence set, so collaborators keep seeing each
 * other (and which file each is on) rather than scattering into per-file rooms.
 *
 * Binding is deliberately deferred until the room confirms `meta["loaded:<p>"]`.
 * Binding to a not-yet-seeded (empty) Y.Text and typing into it would merge
 * those keystrokes into offset 0 of a document that is about to arrive.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { authFetch } from "@/lib/api-client";
import { collabLog } from "./log";
import { colorForUser, type CollabColor } from "./colors";
import { MonacoYBinding, type CollabUser, type RemotePeer } from "./monaco-binding";

/* eslint-disable @typescript-eslint/no-explicit-any */

const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

/** Close codes the server uses to say "do not come back" (backend/collab/room.py). */
/**
 * Codes that mean "stop asking": the user genuinely may not open this project.
 *
 * 4401 is deliberately NOT here. It means a credential was presented and
 * rejected, which on a first attempt usually means the cookie was not sent
 * at all — the normal case when the API is cross-site with the app. Treating
 * it as fatal is what made production show "access revoked" to users who had
 * access: the ticket fallback below would have connected them, but it never
 * ran. 4401 is retried once through ticket mode, and only then given up on.
 */
const FATAL_CLOSE_CODES = new Set([4403, 4404]);
/** No credential was volunteered: authenticate and retry with a ticket. */
const CREDENTIALS_REQUIRED = 4402;
const UNAUTHORIZED = 4401;
const ROOM_FULL = 4429;

const FILE_PREFIX = "file:";
const META_ROOT = "meta";

export type CollabStatus =
  | "disabled"
  /** Enabled, but nobody else is here: no socket is held. */
  | "standby"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "offline";

export interface CollabSession {
  /** The layer is running for this project (not a guest, not disabled). */
  enabled: boolean;
  status: CollabStatus;
  /** The initial document state has arrived from the room. */
  synced: boolean;
  /** Monaco is bound to the CRDT: the host must stop driving it with `value`. */
  bound: boolean;
  role: "Owner" | "Editor" | "Viewer" | null;
  canEdit: boolean;
  peers: RemotePeer[];
  selfColor: CollabColor;
  /** Server-side persistence timestamp (ms) for the active file, if any. */
  savedAt: number | null;
  /** A non-retryable reason the session is not available. */
  fatalError: string | null;
  /** People with this project open right now, from the presence heartbeat. */
  viewers: number;
  registerEditor: (editor: any, monaco: any) => void;
  unregisterEditor: (editor: any) => void;
  /** Local-only undo/redo through the CRDT. Returns false when unavailable. */
  undo: () => boolean;
  redo: () => boolean;
  /** Current CRDT text for the active file, or null when unbound. */
  getText: () => string | null;
  /** Reconnect now (used by the "Reconnecting" indicator's retry affordance). */
  reconnect: () => void;
}

export interface UseCollaborationOptions {
  projectId?: string;
  filePath: string;
  user?: { id?: string | null; name?: string | null; email?: string | null; image?: string | null } | null;
  /** Guests and viewers: see `enabled` / `canEdit`. */
  isGuest?: boolean;
  readOnly?: boolean;
  /** Mirrors remote text into the host's React state (compile, AI, download). */
  onRemoteChange?: (value: string, filePath: string) => void;
  /** Opt out entirely (e.g. NEXT_PUBLIC_COLLAB_ENABLED=0). */
  disabled?: boolean;
}

function wsBase(): string {
  return BACKEND_URL.replace(/^http/i, "ws") + "/ws/collab";
}

export function useCollaboration(options: UseCollaborationOptions): CollabSession {
  const {
    projectId,
    filePath,
    user,
    isGuest = false,
    readOnly = false,
    onRemoteChange,
    disabled = false,
  } = options;

  const envDisabled = process.env.NEXT_PUBLIC_COLLAB_ENABLED === "0";
  const userId = user?.id || null;
  const enabled = !!projectId && !!userId && !isGuest && !disabled && !envDisabled;

  const [status, setStatus] = useState<CollabStatus>(enabled ? "standby" : "disabled");
  const [synced, setSynced] = useState(false);
  const [bound, setBound] = useState(false);
  const [role, setRole] = useState<CollabSession["role"]>(null);
  const [peers, setPeers] = useState<RemotePeer[]>([]);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  /**
   * Whether a realtime room is worth holding right now, from the presence
   * heartbeat. A room costs a websocket, a server concurrency slot, an
   * authoritative CRDT document and a persistence timer for as long as the
   * tab is open — and the common case is one person editing alone, who needs
   * none of it and is served by the REST autosave path. The socket is opened
   * only once the project is actually shared AND a second person has it open.
   */
  const [shouldConnect, setShouldConnect] = useState(false);
  const [viewers, setViewers] = useState(1);

  const docRef = useRef<Y.Doc | null>(null);
  const providerRef = useRef<WebsocketProvider | null>(null);
  const bindingRef = useRef<MonacoYBinding | null>(null);
  const monacoRef = useRef<any>(null);
  const editorsRef = useRef<Set<any>>(new Set());
  const ticketModeRef = useRef(false);
  // Whether a ticket has actually been sent, so a later 4401 can be told
  // apart from the first attempt that carried no credential at all.
  const ticketTriedRef = useRef(false);
  const manualReconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const destroyedRef = useRef(false);
  const presenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onRemoteChangeRef = useRef(onRemoteChange);
  const readOnlyRef = useRef(readOnly);
  const filePathRef = useRef(filePath);

  onRemoteChangeRef.current = onRemoteChange;
  readOnlyRef.current = readOnly;
  filePathRef.current = filePath;

  const localUser: CollabUser = useMemo(
    () => ({
      id: userId || "anonymous",
      name: user?.name || user?.email || "Collaborator",
      email: user?.email || undefined,
      image: user?.image || undefined,
    }),
    [userId, user?.name, user?.email, user?.image],
  );
  // The socket is keyed on the user *id* only. A display name or avatar that
  // loads a moment later must not tear down the connection and drop everyone's
  // presence, so the effects read the current identity through a ref.
  const localUserRef = useRef(localUser);
  localUserRef.current = localUser;

  const selfColor = useMemo(() => colorForUser(localUser.id), [localUser.id]);

  /* ── Ticket (identity proof when the browser will not send cookies) ───── */

  const fetchTicket = useCallback(async (): Promise<string | null> => {
    if (!projectId) return null;
    try {
      const res = await authFetch(`${BACKEND_URL}/api/collab/ticket`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!res.ok) {
        if (res.status === 403) {
          setFatalError("You do not have permission to collaborate on this project.");
        }
        collabLog("COLLAB_AUTH_FAILURE", { stage: "ticket", httpStatus: res.status });
        return null;
      }
      const data = await res.json();
      if (data?.role) setRole(data.role);
      return typeof data?.ticket === "string" ? data.ticket : null;
    } catch (error) {
      collabLog("COLLAB_ERROR", { stage: "ticket", error: String(error) });
      return null;
    }
  }, [projectId]);

  /* ── Presence heartbeat (decides whether a socket is worth opening) ────── */

  useEffect(() => {
    if (!enabled || !projectId) {
      setShouldConnect(false);
      return;
    }
    let cancelled = false;

    const beat = async (leaving = false) => {
      try {
        const res = await authFetch(`${BACKEND_URL}/api/collab/presence`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: projectId, leaving }),
          keepalive: leaving,
        });
        if (!res.ok || cancelled || leaving) return;
        const data = await res.json();
        if (data?.role) setRole(data.role);
        setViewers(typeof data?.viewers === "number" ? data.viewers : 1);
        // Once connected we stay connected until the tab closes: the room's
        // own last-leave path flushes and closes it. Pulling the socket out
        // from under someone mid-keystroke to save a connection is not a
        // trade worth making.
        setShouldConnect((prev) => prev || !!data?.connect);
        if (!cancelled) {
          const every = Math.max(4, Number(data?.poll_interval) || 8) * 1000;
          presenceTimerRef.current = setTimeout(() => void beat(), every);
        }
      } catch {
        if (!cancelled) presenceTimerRef.current = setTimeout(() => void beat(), 15_000);
      }
    };

    void beat();
    return () => {
      cancelled = true;
      if (presenceTimerRef.current) clearTimeout(presenceTimerRef.current);
      presenceTimerRef.current = null;
      // Tell the server at once, so the other editor's socket is not kept
      // alive by a ghost for the whole TTL.
      void beat(true);
    };
  }, [enabled, projectId]);

  /* ── Provider lifecycle (one per project) ────────────────────────────────── */

  useEffect(() => {
    if (!enabled || !projectId || !shouldConnect) {
      setStatus(enabled ? "standby" : "disabled");
      return;
    }

    destroyedRef.current = false;
    const doc = new Y.Doc();
    docRef.current = doc;

    // Cookie auth first: in the standard deployment the API is same-site with
    // the app, so the Better-Auth cookie rides along on the upgrade and no
    // credential ever touches the URL. Ticket mode is the cross-site fallback.
    const provider = new WebsocketProvider(wsBase(), projectId, doc, {
      connect: true,
      params: { file: filePathRef.current },
      resyncInterval: 20_000,
      maxBackoffTime: 10_000,
      shouldReconnect: (event) => {
        if (FATAL_CLOSE_CODES.has(event.code)) return false;
        // Authentication codes are answered by the ticket reconnect below,
        // which fetches a *fresh* credential first. y-websocket's own retry
        // would replay the identical handshake — the same absent cookie, or a
        // ticket already consumed — and fail the same way forever. Returning
        // false parks the provider (`shouldConnect = false`); the explicit
        // provider.connect() in scheduleManualReconnect resumes it.
        if (event.code === CREDENTIALS_REQUIRED || event.code === UNAUTHORIZED) return false;
        if (ticketModeRef.current) return false;
        return true;
      },
    });
    providerRef.current = provider;

    provider.awareness.setLocalState({
      user: localUserRef.current,
      filePath: filePathRef.current,
      selection: null,
      lastActive: Date.now(),
    });

    const scheduleManualReconnect = () => {
      if (destroyedRef.current) return;
      if (manualReconnectRef.current) return;
      const attempt = reconnectAttemptsRef.current;
      const delay = Math.min(10_000, 500 * 2 ** Math.min(attempt, 5));
      reconnectAttemptsRef.current = attempt + 1;
      manualReconnectRef.current = setTimeout(async () => {
        manualReconnectRef.current = null;
        if (destroyedRef.current) return;
        const ticket = await fetchTicket();
        if (destroyedRef.current) return;
        if (ticket) {
          ticketTriedRef.current = true;
          provider.params = { ticket, file: filePathRef.current };
          collabLog("COLLAB_RECONNECT", { projectId, attempt, auth: "ticket" });
          provider.connect();
        } else {
          scheduleManualReconnect();
        }
      }, delay);
    };

    const handleStatus = (event: { status: string }) => {
      if (destroyedRef.current) return;
      if (event.status === "connected") {
        reconnectAttemptsRef.current = 0;
        ticketTriedRef.current = false;
        setStatus("connected");
        collabLog("COLLAB_CONNECT", { projectId, auth: ticketModeRef.current ? "ticket" : "cookie" });
      } else if (event.status === "connecting") {
        setStatus((prev) => (prev === "connected" ? "reconnecting" : "connecting"));
      } else {
        setStatus("reconnecting");
      }
    };

    const handleSync = (isSynced: boolean) => {
      if (destroyedRef.current) return;
      setSynced(isSynced);
      if (isSynced) collabLog("COLLAB_SYNC", { projectId, file: filePathRef.current });
    };

    const handleClose = (event: CloseEvent | null) => {
      if (destroyedRef.current || !event) return;
      collabLog("COLLAB_DISCONNECT", { projectId, code: event.code, reason: event.reason });

      if (FATAL_CLOSE_CODES.has(event.code)) {
        setStatus("offline");
        setFatalError(
          event.code === 4404
            ? "This project no longer exists."
            : "Your access to this project was revoked. Reload to continue.",
        );
        return;
      }
      if (event.code === ROOM_FULL) {
        setStatus("offline");
        setFatalError("This project has too many live editors right now.");
        return;
      }

      // A 4401 that survives ticket mode is a real rejection: we presented a
      // freshly issued, signed ticket for this project and the server refused
      // it. Anything earlier is "we have not proved who we are yet".
      if (event.code === UNAUTHORIZED && ticketModeRef.current && ticketTriedRef.current) {
        setStatus("offline");
        setFatalError("Your access to this project was revoked. Reload to continue.");
        return;
      }

      // Either the server asked for a credential (4402), the cookie was not
      // attached (cross-site deployment: 4401 or a bare 1006), or the link
      // dropped. In every one of those cases the answer is the same — get a
      // ticket and try again — so this is the one path to ticket mode.
      if (!ticketModeRef.current && (event.code === CREDENTIALS_REQUIRED
          || event.code === UNAUTHORIZED || !provider.synced)) {
        ticketModeRef.current = true;
        collabLog("COLLAB_RECONNECT", { projectId, switchingTo: "ticket", code: event.code });
      }
      setStatus("reconnecting");
      if (ticketModeRef.current) scheduleManualReconnect();
    };

    const handleConnectionError = (event: Event) => {
      if (destroyedRef.current) return;
      collabLog("COLLAB_ERROR", { projectId, stage: "connection", type: event?.type });
    };

    provider.on("status", handleStatus);
    provider.on("sync", handleSync);
    provider.on("connection-close", handleClose);
    provider.on("connection-error", handleConnectionError);

    // Learn our role up front; the ticket is also kept warm for the fallback.
    void fetchTicket();

    const handleOffline = () => {
      if (!destroyedRef.current) setStatus("offline");
    };
    const handleOnline = () => {
      if (destroyedRef.current) return;
      setStatus("reconnecting");
      reconnectAttemptsRef.current = 0;
      if (ticketModeRef.current) scheduleManualReconnect();
      else provider.connect();
    };
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);

    return () => {
      destroyedRef.current = true;
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      if (manualReconnectRef.current) {
        clearTimeout(manualReconnectRef.current);
        manualReconnectRef.current = null;
      }
      bindingRef.current?.destroy();
      bindingRef.current = null;
      provider.off("status", handleStatus);
      provider.off("sync", handleSync);
      provider.off("connection-close", handleClose);
      provider.off("connection-error", handleConnectionError);
      // Clears our awareness state for everyone else before the socket drops.
      try {
        provider.awareness.setLocalState(null);
      } catch {
        /* provider already torn down */
      }
      provider.destroy();
      doc.destroy();
      providerRef.current = null;
      docRef.current = null;
      ticketModeRef.current = false;
      reconnectAttemptsRef.current = 0;
      setBound(false);
      setSynced(false);
      setPeers([]);
      collabLog("COLLAB_LEAVE", { projectId });
    };
    // `filePath` and the display fields of `localUser` are intentionally
    // excluded: switching files must only re-bind inside the same room (see
    // the binding effect), and a late-loading avatar must not reconnect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, projectId, userId, shouldConnect, fetchTicket]);

  /* ── Announce the active file; the room seeds it on this signal ──────────── */

  useEffect(() => {
    const provider = providerRef.current;
    if (!enabled || !provider) return;
    try {
      provider.awareness.setLocalState({
        ...provider.awareness.getLocalState(),
        user: localUser,
        filePath,
        selection: null,
        lastActive: Date.now(),
      });
      // Also on the query string, so a fresh connection seeds the file during
      // the handshake instead of one awareness round trip later.
      provider.params = { ...provider.params, file: filePath };
    } catch (error) {
      collabLog("COLLAB_ERROR", { stage: "announce_file", error: String(error) });
    }
  }, [enabled, filePath, localUser, synced]);

  /* ── Bind Monaco once the room says this file is seeded ─────────────────── */

  const [editorsNonce, setEditorsNonce] = useState(0);

  const registerEditor = useCallback((editor: any, monaco: any) => {
    if (!editor) return;
    monacoRef.current = monaco || monacoRef.current;
    if (editorsRef.current.has(editor)) return;
    editorsRef.current.add(editor);
    if (bindingRef.current) {
      // Already bound (EditorLayout mounts a desktop and a mobile instance
      // over one shared model): attach the new instance's cursor decorations
      // and leave the binding alone. Bumping the nonce here would re-run the
      // binding effect and rebuild the UndoManager, throwing away the undo
      // history the user had accumulated.
      bindingRef.current.addEditor(editor);
      return;
    }
    setEditorsNonce((n) => n + 1);
  }, []);

  const unregisterEditor = useCallback((editor: any) => {
    if (!editor) return;
    editorsRef.current.delete(editor);
    bindingRef.current?.removeEditor(editor);
  }, []);

  useEffect(() => {
    if (!enabled || !synced) return;
    const doc = docRef.current;
    const provider = providerRef.current;
    const monaco = monacoRef.current;
    const editor = Array.from(editorsRef.current)[0];
    const model = editor?.getModel?.();
    if (!doc || !provider || !monaco || !model) return;

    const meta = doc.getMap(META_ROOT);
    let binding: MonacoYBinding | null = null;
    let cancelled = false;

    const tryBind = () => {
      if (cancelled || binding) return;
      if (meta.get(`loaded:${filePath}`) !== true) return;

      binding = new MonacoYBinding({
        monaco,
        model,
        ytext: doc.getText(FILE_PREFIX + filePath),
        awareness: provider.awareness,
        filePath,
        localUser,
        readOnly: readOnlyRef.current,
        onPeersChange: (next) => {
          if (!cancelled) setPeers(next);
        },
        onRemoteChange: (value) => {
          if (!cancelled) onRemoteChangeRef.current?.(value, filePath);
        },
      });
      bindingRef.current = binding;
      editorsRef.current.forEach((instance) => binding?.addEditor(instance));
      binding.publishPresence();
      setBound(true);
      // The host mirrors the seeded text into React state (compile, AI, save).
      onRemoteChangeRef.current?.(model.getValue(), filePath);
    };

    const onMeta = () => {
      tryBind();
      const saved = meta.get(`saved:${filePath}`) as { at?: number } | undefined;
      if (saved && typeof saved.at === "number") setSavedAt(saved.at);
    };

    meta.observe(onMeta);
    tryBind();
    onMeta();

    return () => {
      cancelled = true;
      meta.unobserve(onMeta);
      binding?.destroy();
      if (bindingRef.current === binding) bindingRef.current = null;
      setBound(false);
      setPeers([]);
    };
  }, [enabled, synced, filePath, localUser, editorsNonce]);

  useEffect(() => {
    bindingRef.current?.setReadOnly(readOnly);
  }, [readOnly, bound]);

  /* ── Public operations ──────────────────────────────────────────────────── */

  const undo = useCallback(() => {
    const manager = bindingRef.current?.undoManager;
    if (!manager || manager.undoStack.length === 0) return false;
    manager.undo();
    return true;
  }, []);

  const redo = useCallback(() => {
    const manager = bindingRef.current?.undoManager;
    if (!manager || manager.redoStack.length === 0) return false;
    manager.redo();
    return true;
  }, []);

  const getText = useCallback(() => {
    const doc = docRef.current;
    if (!doc || !bindingRef.current) return null;
    return doc.getText(FILE_PREFIX + filePathRef.current).toString();
  }, []);

  const reconnect = useCallback(() => {
    const provider = providerRef.current;
    if (!provider) return;
    reconnectAttemptsRef.current = 0;
    setFatalError(null);
    if (ticketModeRef.current) {
      void fetchTicket().then((ticket) => {
        if (!ticket || destroyedRef.current) return;
        provider.params = { ticket, file: filePathRef.current };
        provider.connect();
      });
    } else {
      provider.connect();
    }
  }, [fetchTicket]);

  return {
    enabled,
    status: enabled ? status : "disabled",
    synced,
    bound,
    role,
    canEdit: !readOnly && role !== "Viewer",
    peers,
    selfColor,
    savedAt,
    fatalError,
    viewers,
    registerEditor,
    unregisterEditor,
    undo,
    redo,
    getText,
    reconnect,
  };
}
