/**
 * Mentions: selections the user pins to a chat message with "@ Mention".
 * Pure and DOM-free so scripts/test_mentions.mjs can run it under plain node.
 */
export interface MentionRef {
  id: string;
  file: string;
  start_line: number;
  end_line: number;
  text: string;
  label: string;
}

export const MAX_MENTIONS = 8;
// Keeps eight pasted-in chunks from swamping the model's context.
export const MAX_MENTION_CHARS = 4000;

export function mentionLabel(file: string, startLine: number, endLine: number): string {
  const base = file.slice(file.lastIndexOf("/") + 1);
  const range = startLine === endLine ? `L${startLine}` : `L${startLine}–L${endLine}`;
  return `${base} ${range}`;
}

export function makeMention(file: string, startLine: number, endLine: number, text: string): MentionRef {
  return {
    id: `${file}:${startLine}:${endLine}`,
    file,
    start_line: startLine,
    end_line: endLine,
    text: text.length > MAX_MENTION_CHARS ? `${text.slice(0, MAX_MENTION_CHARS)}\n…` : text,
    label: mentionLabel(file, startLine, endLine),
  };
}

/**
 * A whole file pinned to the message (typed as "@main.tex"). Line numbers are 0
 * and the text empty: the backend sees only the path, so the agent opens the
 * file itself. The chip shows the bare file name rather than "main.tex L0".
 */
export function makeFileMention(file: string): MentionRef {
  return {
    id: `${file}:file`,
    file,
    start_line: 0,
    end_line: 0,
    text: "",
    label: file.slice(file.lastIndexOf("/") + 1),
  };
}

export function addMention(
  list: MentionRef[],
  next: MentionRef,
): { list: MentionRef[]; error: string | null } {
  const at = list.findIndex((m) => m.id === next.id);
  if (at >= 0) {
    const copy = list.slice();
    copy[at] = next;
    return { list: copy, error: null };
  }
  if (list.length >= MAX_MENTIONS) {
    return { list, error: `You can mention up to ${MAX_MENTIONS} selections.` };
  }
  return { list: [...list, next], error: null };
}

export function removeMention(list: MentionRef[], id: string): MentionRef[] {
  return list.filter((m) => m.id !== id);
}
