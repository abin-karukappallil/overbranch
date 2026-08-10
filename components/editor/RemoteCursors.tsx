"use client";

import React, { useEffect, useRef, useState } from "react";
import type { CursorPresence } from "@/lib/realtime/presence";

interface RemoteCursorsProps {
  cursors: CursorPresence[];
  editorElement: HTMLElement | null;
  /** Function that converts a {lineNumber, column} position to pixel coordinates */
  getPixelPosition?: (pos: { lineNumber: number; column: number }) => { top: number; left: number } | null;
}

/**
 * Remote cursor overlay (spec section 2).
 *
 * - Absolutely positioned, pointer-events: none
 * - Renders colored carets with collaborator name tooltips
 * - Lerp interpolation between last two known positions
 * - Idle cursors fade via CSS transition
 */
export function RemoteCursors({ cursors, editorElement, getPixelPosition }: RemoteCursorsProps) {
  if (!editorElement || !getPixelPosition) return null;

  return (
    <div
      className="absolute inset-0 pointer-events-none z-50 overflow-hidden"
      style={{ position: "absolute" }}
    >
      {cursors.map((cursor) => {
        if (!cursor.cursorPos) return null;

        const pixelPos = getPixelPosition(cursor.cursorPos);
        if (!pixelPos) return null;

        const isIdle = cursor.status === "idle";

        return (
          <RemoteCursorCaret
            key={cursor.userId}
            name={cursor.name}
            color={cursor.color}
            top={pixelPos.top}
            left={pixelPos.left}
            isIdle={isIdle}
          />
        );
      })}
    </div>
  );
}

// ─── Individual Cursor Caret ────────────────────────────────────────

interface RemoteCursorCaretProps {
  name: string;
  color: string;
  top: number;
  left: number;
  isIdle: boolean;
}

function RemoteCursorCaret({ name, color, top, left, isIdle }: RemoteCursorCaretProps) {
  const [displayPos, setDisplayPos] = useState({ top, left });
  const prevPosRef = useRef({ top, left });

  // Lerp interpolation between positions (spec section 2)
  useEffect(() => {
    const startPos = prevPosRef.current;
    const endPos = { top, left };
    const startTime = performance.now();
    const duration = 80; // 80ms interpolation

    let animId: number;

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);

      // Ease-out curve
      const eased = 1 - (1 - t) * (1 - t);

      setDisplayPos({
        top: startPos.top + (endPos.top - startPos.top) * eased,
        left: startPos.left + (endPos.left - startPos.left) * eased,
      });

      if (t < 1) {
        animId = requestAnimationFrame(animate);
      } else {
        prevPosRef.current = endPos;
      }
    };

    animId = requestAnimationFrame(animate);

    return () => cancelAnimationFrame(animId);
  }, [top, left]);

  return (
    <div
      className="absolute transition-opacity duration-500"
      style={{
        top: displayPos.top,
        left: displayPos.left,
        opacity: isIdle ? 0.4 : 1,
        zIndex: 100,
      }}
    >
      {/* Cursor line */}
      <div
        className="w-0.5 rounded-full"
        style={{
          backgroundColor: color,
          height: 18,
          boxShadow: `0 0 4px ${color}40`,
        }}
      />
    </div>
  );
}
