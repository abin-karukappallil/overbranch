/**
 * EditHistoryStore.ts — Persistent AI Edit History
 *
 * Captures full multi-file snapshots, cursor position, scroll state,
 * and prompt metadata before and after AI edits for reliable revert/reapply.
 */

export interface EditHistory {
  id: string;
  timestamp: number;
  model: string;
  prompt: string;
  files: string[];
  beforeCode: Record<string, string>;
  afterCode: Record<string, string>;
  cursorState: {
    file: string;
    line: number;
    column: number;
    scrollTop: number;
  };
  isReverted?: boolean;
}

const MAX_HISTORY = 30;

export class EditHistoryStore {
  private entries: EditHistory[] = [];
  private storageKey: string;

  constructor(projectId: string) {
    this.storageKey = `overbranch_${projectId || "default"}_edit_history_v2`;
    this.loadFromStorage();
  }

  private loadFromStorage(): void {
    if (typeof window === "undefined") return;
    try {
      const saved = localStorage.getItem(this.storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          this.entries = parsed;
        }
      }
    } catch (e) {
      console.warn("EditHistoryStore: failed to load history from storage", e);
    }
  }

  private saveToStorage(): void {
    if (typeof window === "undefined") return;
    try {
      const toSave = this.entries.slice(-MAX_HISTORY);
      localStorage.setItem(this.storageKey, JSON.stringify(toSave));
    } catch (e) {
      console.warn("EditHistoryStore: failed to save history to storage", e);
    }
  }

  pushEdit(entry: EditHistory): void {
    // Avoid duplicate entries
    const existingIndex = this.entries.findIndex((e) => e.id === entry.id);
    if (existingIndex >= 0) {
      this.entries[existingIndex] = entry;
    } else {
      this.entries.push(entry);
    }

    if (this.entries.length > MAX_HISTORY) {
      this.entries = this.entries.slice(-MAX_HISTORY);
    }
    this.saveToStorage();
  }

  hasEntry(id: string): boolean {
    return this.entries.some((e) => e.id === id);
  }

  getEntry(id: string): EditHistory | undefined {
    return this.entries.find((e) => e.id === id);
  }

  getEntryByMessageId(messageId: string): EditHistory | undefined {
    return this.entries.find((e) => e.id === messageId);
  }

  revertEdit(id: string): EditHistory | null {
    const entry = this.entries.find((e) => e.id === id);
    if (!entry) return null;

    entry.isReverted = true;
    this.saveToStorage();
    return entry;
  }

  reapplyEdit(id: string): EditHistory | null {
    const entry = this.entries.find((e) => e.id === id);
    if (!entry) return null;

    entry.isReverted = false;
    this.saveToStorage();
    return entry;
  }

  isReverted(id: string): boolean {
    const entry = this.entries.find((e) => e.id === id);
    return entry?.isReverted ?? false;
  }

  getHistory(): EditHistory[] {
    return [...this.entries];
  }

  clear(): void {
    this.entries = [];
    if (typeof window === "undefined") return;
    try {
      localStorage.removeItem(this.storageKey);
    } catch (_) {}
  }
}
