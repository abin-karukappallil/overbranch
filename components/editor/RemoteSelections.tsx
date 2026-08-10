"use client";

import React from "react";
import type { CursorPresence } from "@/lib/realtime/presence";

interface RemoteSelectionsProps {
  cursors: CursorPresence[];
  editorElement: HTMLElement | null;
  /** Convert a line/col range to pixel dimensions */
  getSelectionRects?: (selection: NonNullable<CursorPresence["selection"]>) => Array<{
    top: number;
    left: number;
    width: number;
    height: number;
  }>;
}

/**
 * Remote selection highlights overlay (spec section 4).
 *
 * Renders translucent colored rectangles for each collaborator's selection range.
 * Automatically disappears when a collaborator disconnects (Presence leave event).
 */
export function RemoteSelections({ cursors, editorElement, getSelectionRects }: RemoteSelectionsProps) {
  if (!editorElement || !getSelectionRects) return null;

  return (
    <div
      className="absolute inset-0 pointer-events-none z-40 overflow-hidden"
      style={{ position: "absolute" }}
    >
      {cursors.map((cursor) => {
        if (!cursor.selection) return null;

        // Skip if the selection is collapsed (start === end)
        const s = cursor.selection;
        if (
          s.startLineNumber === s.endLineNumber &&
          s.startColumn === s.endColumn
        ) {
          return null;
        }

        const rects = getSelectionRects(s);
        if (!rects || rects.length === 0) return null;

        return (
          <div key={`selection-${cursor.userId}`}>
            {rects.map((rect, i) => (
              <div
                key={`${cursor.userId}-rect-${i}`}
                className="absolute rounded-sm transition-all duration-100"
                style={{
                  top: rect.top,
                  left: rect.left,
                  width: rect.width,
                  height: rect.height,
                  backgroundColor: `${cursor.color}25`,
                  borderLeft: i === 0 ? `2px solid ${cursor.color}60` : undefined,
                  borderRight: i === rects.length - 1 ? `2px solid ${cursor.color}60` : undefined,
                }}
              />
            ))}

            {/* Selection label near the start */}
            {rects[0] && (
              <div
                className="absolute whitespace-nowrap px-1 py-0.5 rounded text-[8px] font-medium text-white/80 shadow-sm"
                style={{
                  backgroundColor: `${cursor.color}90`,
                  top: rects[0].top - 14,
                  left: rects[0].left,
                }}
              >
                {cursor.name}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
