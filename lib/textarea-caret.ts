/**
 * Where is the caret inside a <textarea>? The textarea exposes no such API, so
 * the usual trick is used: copy its text, up to the caret, into an invisible
 * <div> styled identically, and measure a marker <span> at the end of it.
 *
 * The DOM work is a thin wrapper (`getCaretCoords`); the arithmetic is in
 * `computeCaretCoords`, which takes already-measured numbers so
 * scripts/test_textarea_caret.mjs can test it under plain node.
 */

export interface CaretCoords {
  left: number;
  top: number;
  height: number;
}

export interface MarkerMeasure {
  offsetLeft: number;
  offsetTop: number;
  offsetHeight: number;
}

export interface CaretOffsets {
  borderLeft: number;
  borderTop: number;
  scrollLeft: number;
  scrollTop: number;
}

/**
 * Marker position -> caret position relative to the textarea's top-left
 * (border box). The marker's offsets are measured from the mirror's padding
 * edge, so the border is added back; scrolling moves the text under the
 * caret, so it is subtracted.
 */
export function computeCaretCoords(marker: MarkerMeasure, offsets: CaretOffsets): CaretCoords {
  return {
    left: marker.offsetLeft + offsets.borderLeft - offsets.scrollLeft,
    top: marker.offsetTop + offsets.borderTop - offsets.scrollTop,
    height: marker.offsetHeight,
  };
}

// Every property that changes where a character lands.
const MIRRORED_PROPERTIES = [
  "direction",
  "boxSizing",
  "borderTopWidth",
  "borderRightWidth",
  "borderBottomWidth",
  "borderLeftWidth",
  "borderTopStyle",
  "borderRightStyle",
  "borderBottomStyle",
  "borderLeftStyle",
  "paddingTop",
  "paddingRight",
  "paddingBottom",
  "paddingLeft",
  "fontStyle",
  "fontVariant",
  "fontWeight",
  "fontStretch",
  "fontSize",
  "fontSizeAdjust",
  "lineHeight",
  "fontFamily",
  "textAlign",
  "textTransform",
  "textIndent",
  "textDecoration",
  "letterSpacing",
  "wordSpacing",
  "tabSize",
  "whiteSpace",
  "wordWrap",
  "overflowWrap",
  "wordBreak",
] as const;

const ZERO_WIDTH = "​";

export function getCaretCoords(textarea: HTMLTextAreaElement, caretIndex: number): CaretCoords {
  const style = window.getComputedStyle(textarea);
  const mirror = document.createElement("div");
  const target = mirror.style as unknown as Record<string, string>;
  const source = style as unknown as Record<string, string>;
  for (const prop of MIRRORED_PROPERTIES) target[prop] = source[prop];

  const px = (value: string) => parseFloat(value) || 0;
  const borderLeft = px(style.borderLeftWidth);
  const borderRight = px(style.borderRightWidth);
  // clientWidth is the padding box minus any scrollbar; the mirror gets the
  // same content width whichever box-sizing the textarea uses.
  const width =
    style.boxSizing === "border-box"
      ? textarea.clientWidth + borderLeft + borderRight
      : textarea.clientWidth - px(style.paddingLeft) - px(style.paddingRight);

  mirror.style.position = "absolute";
  mirror.style.visibility = "hidden";
  mirror.style.whiteSpace = "pre-wrap";
  mirror.style.wordWrap = "break-word";
  mirror.style.overflow = "hidden";
  mirror.style.top = "0";
  mirror.style.left = "-9999px";
  mirror.style.width = `${width}px`;

  mirror.textContent = textarea.value.slice(0, Math.max(0, caretIndex));
  const marker = document.createElement("span");
  marker.textContent = ZERO_WIDTH;
  mirror.appendChild(marker);

  document.body.appendChild(mirror);
  try {
    return computeCaretCoords(
      {
        offsetLeft: marker.offsetLeft,
        offsetTop: marker.offsetTop,
        offsetHeight: marker.offsetHeight,
      },
      {
        borderLeft,
        borderTop: px(style.borderTopWidth),
        scrollLeft: textarea.scrollLeft,
        scrollTop: textarea.scrollTop,
      },
    );
  } finally {
    document.body.removeChild(mirror);
  }
}
