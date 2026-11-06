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
 * prefix stays dark in light mode.
 */

import React, { memo, useMemo, useState } from "react";
import { Wifi, WifiOff, RotateCw, Users, UserRound } from "lucide-react";
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
      <span className="flex items-center gap-1 text-ob-positive" title="Live — changes sync instantly">
        <Wifi className="size-3" />
        <span className="hidden lg:inline font-mono text-xs">Live</span>
      </span>
    );
  }
  if (status === "standby") {
    return (
      <span
        className="flex items-center gap-1 text-ob-muted"
        title="Solo editing session — realtime sync starts when a collaborator joins"
      >
        <UserRound className="size-3" />
        <span className="hidden lg:inline font-mono text-xs">Solo</span>
      </span>
    );
  }
  if (status === "connecting" || status === "reconnecting") {
    return (
      <span
        className="flex items-center gap-1 text-ob-warn"
        title="Reconnecting — changes sync when link returns"
      >
        <RotateCw className="size-3 animate-spin" />
        <span className="hidden lg:inline font-mono text-xs">{status === "connecting" ? "Connecting" : "Reconnecting"}</span>
      </span>
    );
  }
  return (
    <span
      className="flex items-center gap-1 text-ob-negative"
      title="Offline — edits kept locally"
    >
      <WifiOff className="size-3" />
      <span className="hidden lg:inline font-mono text-xs">Offline</span>
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
        className={`size-6 rounded-full flex items-center justify-center text-[10px] font-medium text-white overflow-hidden ring-1 ring-ob-line transition-opacity ${
          dimmed ? "opacity-50" : "opacity-100"
        }`}
        style={{ backgroundColor: color.solid }}
        aria-label={name}
      >
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={image} alt={name} className="size-full object-cover" />
        ) : (
          initialsForName(name)
        )}
      </div>
      {hovered && (
        <div className="absolute right-0 top-8 z-50 whitespace-nowrap rounded-lg border border-ob-line bg-ob-card px-2.5 py-1.5 shadow-xl text-ob-text">
          <div className="text-xs font-medium text-ob-text">{name}</div>
          {subtitle && (
            <div className="text-[10px] font-mono text-ob-muted">{subtitle}</div>
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
      className="hidden xl:flex items-center gap-2 h-8 px-2.5 rounded-lg border border-ob-line bg-ob-card text-xs font-mono text-ob-muted shrink-0"
      data-testid="collab-presence-bar"
    >
      <StatusDot status={status} />

      <span className="w-px h-4 bg-ob-line" />

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
        <span className="flex items-center gap-0.5 text-ob-muted" title={`${overflow} more live`}>
          <Users className="size-3" />+{overflow}
        </span>
      )}

      {fatalError && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="ml-1 px-1.5 py-0.5 rounded border border-ob-negative/20 bg-ob-raised text-ob-negative transition-colors cursor-pointer text-[10px]"
          title={fatalError}
        >
          Retry
        </button>
      )}
    </div>
  );
}

export const CollabPresenceBar = memo(CollabPresenceBarImpl);
