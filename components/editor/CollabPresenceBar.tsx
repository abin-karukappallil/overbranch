"use client";

/**
 * components/editor/CollabPresenceBar.tsx — Live collaborators & link state
 * =========================================================================
 * Sits in the editor header next to the existing CollaboratorAvatars (which
 * lists *everyone invited*; this lists *who is here right now*).
 *
 * Deliberately memoized and driven only by `peers` / `status`: presence changes
 * whenever anyone moves a cursor, so re-rendering the editor shell on every
 * awareness tick would be the most expensive thing in the app.
 *
 * Every surface is a `light dark:` pair — a hardcoded hex with no `dark:`
 * prefix stays dark in light mode (see OVERVIEW.md, Feature 29).
 */

import React, { memo, useMemo, useState } from "react";
import { Wifi, WifiOff, RotateCw, Users } from "lucide-react";
import type { RemotePeer } from "@/lib/collab/monaco-binding";
import { initialsForName, type CollabColor } from "@/lib/collab/colors";
import type { CollabStatus } from "@/lib/collab/useCollaboration";

interface CollabPresenceBarProps {
  status: CollabStatus;
  peers: RemotePeer[];
  selfName: string;
  selfColor: CollabColor;
  selfImage?: string | null;
  activeFilePath: string;
  fatalError?: string | null;
  onRetry?: () => void;
}

const MAX_VISIBLE = 4;

function StatusDot({ status }: { status: CollabStatus }) {
  if (status === "connected") {
    return (
      <span className="flex items-center gap-1 text-emerald-600 dark:text-[#10B981]" title="Live — changes sync instantly">
        <Wifi className="w-3 h-3" />
        <span className="hidden lg:inline">Live</span>
      </span>
    );
  }
  if (status === "connecting" || status === "reconnecting") {
    return (
      <span
        className="flex items-center gap-1 text-amber-600 dark:text-[#FF9900]"
        title="Reconnecting — you can keep editing; changes sync when the link returns"
      >
        <RotateCw className="w-3 h-3 animate-spin" />
        <span className="hidden lg:inline">{status === "connecting" ? "Connecting" : "Reconnecting"}</span>
      </span>
    );
  }
  return (
    <span
      className="flex items-center gap-1 text-rose-600 dark:text-rose-400"
      title="Offline — edits are kept locally and sync on reconnect"
    >
      <WifiOff className="w-3 h-3" />
      <span className="hidden lg:inline">Offline</span>
    </span>
  );
}

function PeerAvatar({
  name,
  image,
  color,
  subtitle,
  dimmed,
}: {
  name: string;
  image?: string | null;
  color: CollabColor;
  subtitle?: string;
  dimmed?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-archivo font-bold text-white overflow-hidden ring-2 transition-opacity ${
          dimmed ? "opacity-50" : "opacity-100"
        }`}
        style={{ backgroundColor: color.solid, boxShadow: `0 0 0 2px ${color.solid}33` }}
        aria-label={name}
      >
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={image} alt={name} className="w-full h-full object-cover" />
        ) : (
          initialsForName(name)
        )}
      </div>
      {hovered && (
        <div className="absolute right-0 top-8 z-50 whitespace-nowrap rounded-lg border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] px-2 py-1 shadow-xl">
          <div className="text-[11px] font-archivo font-bold text-slate-900 dark:text-[#E2E4E9]">{name}</div>
          {subtitle && (
            <div className="text-[10px] font-mono text-slate-500 dark:text-[#9E9E9E]">{subtitle}</div>
          )}
        </div>
      )}
    </div>
  );
}

function CollabPresenceBarImpl({
  status,
  peers,
  selfName,
  selfColor,
  selfImage,
  activeFilePath,
  fatalError,
  onRetry,
}: CollabPresenceBarProps) {
  const sorted = useMemo(
    () =>
      [...peers].sort((a, b) => {
        if (a.sameFile !== b.sameFile) return a.sameFile ? -1 : 1;
        return b.lastActive - a.lastActive;
      }),
    [peers],
  );

  const visible = sorted.slice(0, MAX_VISIBLE);
  const overflow = sorted.length - visible.length;

  return (
    <div
      className="hidden sm:flex items-center gap-2 h-8 px-2.5 rounded-lg bg-slate-100 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] text-[11px] font-mono shrink-0"
      data-testid="collab-presence-bar"
    >
      <StatusDot status={status} />

      <span className="w-px h-4 bg-slate-200 dark:bg-[#282A30]" />

      <div className="flex items-center -space-x-1.5">
        <PeerAvatar
          name={`${selfName} (you)`}
          image={selfImage}
          color={selfColor}
          subtitle={activeFilePath}
        />
        {visible.map((peer) => (
          <PeerAvatar
            key={peer.clientId}
            name={peer.user.name}
            image={peer.user.image}
            color={peer.color}
            dimmed={peer.idle}
            subtitle={
              peer.sameFile
                ? `${peer.filePath || activeFilePath}${peer.idle ? " · idle" : ""}`
                : `in ${peer.filePath || "another file"}`
            }
          />
        ))}
      </div>

      {overflow > 0 && (
        <span className="flex items-center gap-0.5 text-slate-500 dark:text-[#9E9E9E]" title={`${overflow} more live`}>
          <Users className="w-3 h-3" />+{overflow}
        </span>
      )}

      {fatalError && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="ml-1 px-1.5 py-0.5 rounded bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-rose-700 dark:text-rose-300 hover:bg-rose-100 dark:hover:bg-rose-500/20 transition-colors cursor-pointer"
          title={fatalError}
        >
          Retry
        </button>
      )}
    </div>
  );
}

export const CollabPresenceBar = memo(CollabPresenceBarImpl);
