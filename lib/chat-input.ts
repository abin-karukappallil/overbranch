/**
 * lib/chat-input.ts — what the Enter key does in the agent chat box.
 *
 * On a desktop keyboard Enter sends and Shift+Enter makes a new line. A phone
 * keyboard has no Shift+Enter, so Enter-to-send left no way to type a second
 * line at all: every newline sent the message half-written. On a touch device
 * Enter therefore makes a new line and the Send button sends, which is what
 * every phone messaging app does.
 *
 * `(pointer: coarse)` is the right test rather than a width breakpoint: it asks
 * whether the PRIMARY input is a finger, so a narrow desktop window keeps
 * Enter-to-send, and a tablet with a hardware keyboard — which does have
 * Shift+Enter — is the one case this gets wrong, in the harmless direction.
 */

export type EnterKeyEvent = {
  key: string;
  shiftKey?: boolean;
  /** `KeyboardEvent.isComposing`, via React's `nativeEvent`. */
  isComposing?: boolean;
  /** 229 is what every major browser reports while an IME is composing. */
  keyCode?: number;
  /** Whether the only keyboard here is the on-screen one. */
  softKeyboardOnly?: boolean;
};

/**
 * Whether this keypress should send the message.
 *
 * False means "let the textarea have it", which inserts a newline for Enter.
 *
 * The IME guard matters on both platforms: while a Chinese, Japanese, Korean or
 * Vietnamese input method is composing, Enter *commits the candidate word* and
 * must never reach the send path — otherwise the message goes half-typed, which
 * is the same bug as the phone one with a different cause.
 */
export function shouldSendOnEnter(e: EnterKeyEvent): boolean {
  if (e.key !== "Enter") return false;
  if (e.isComposing || e.keyCode === 229) return false;
  if (e.shiftKey) return false;
  if (e.softKeyboardOnly) return false;
  return true;
}

/** The media query that decides it, in one place. */
export const COARSE_POINTER_QUERY = "(pointer: coarse)";
