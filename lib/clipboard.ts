/**
 * Clipboard helpers shared by the editor toolbar, the mobile touch callout and
 * the chat copy buttons.
 *
 * These were previously inlined in `EditorLayout.handleCustomCopy` /
 * `handleCustomPaste` (which were never rendered). They are lifted here because
 * the mobile callout needs exactly the same fallbacks, and because iOS Safari
 * needs a paste path that neither of those functions had.
 */

/**
 * Writes `text` to the clipboard. Returns false only when every path failed.
 *
 * `navigator.clipboard.writeText` needs a secure context and, in some browsers,
 * an active user gesture; the hidden-textarea `execCommand("copy")` fallback
 * works in the cases it does not.
 */
export async function copyText(text: string): Promise<boolean> {
  if (!text) return false;

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) {
    // fall through to execCommand
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.top = "0";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch (_) {
    return false;
  }
}

/**
 * Reads the clipboard, or returns null when the browser will not allow it.
 *
 * iOS Safari does not implement `readText` at all (and Firefox gates it behind
 * a pref), so a null here is expected, not exceptional. Callers that must still
 * offer Paste need a user-driven fallback — see `MobileEditorAssist`, which
 * focuses a real textarea so the OS can show its own paste affordance.
 */
export async function readClipboard(): Promise<string | null> {
  try {
    if (navigator.clipboard?.readText) {
      const text = await navigator.clipboard.readText();
      return text ?? null;
    }
  } catch (_) {
    // Permission denied or unsupported.
  }
  return null;
}

/** True when the browser can read the clipboard without a DOM paste event. */
export function canReadClipboard(): boolean {
  return typeof navigator !== "undefined" && !!navigator.clipboard?.readText;
}
