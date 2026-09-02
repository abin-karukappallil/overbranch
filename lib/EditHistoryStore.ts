/**
 * EditHistoryStore.ts — AI Edit History with Patch/Inverse-Patch Storage
 *
 * Stores every accepted AI edit for revert/reapply functionality.
 * Each entry captures the full document state before and after the edit,
 * enabling force-revert regardless of subsequent manual edits.
 */

import type { EditItem } from "@/components/editor/InlineDiffEditor";

export interface EditHistoryEntry {
  id: string;
  messageId: string;         // Chat message ID this edit came from
  prompt: string;            // User prompt that triggered this edit
  timestamp: number;         // When the edit was accepted
  filePath: string;          // File path that was edited
  edits: EditItem[];         // The edit items that were applied
  codeBeforeEdit: string;    // Full document state before this edit
  codeAfterEdit: string;     // Full document state after this edit
  isReverted: boolean;       // Whether this edit has been reverted
}

const MAX_HISTORY = 50;

export class EditHistoryStore {
  private entries: EditHistoryEntry[] = [];
  private storageKey: string;

  constructor(projectId: string) {
    this.storageKey = `overbranch_${projectId}_edit_history`;
    this.loadFromStorage();
  }

  private loadFromStorage(): void {
    try {
      const saved = localStorage.getItem(this.storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          this.entries = parsed;
        }
      }
    } catch (e) {
      console.warn("Failed to load edit history from localStorage:", e);
    }
  }

  private saveToStorage(): void {
    try {
      // Only persist metadata, not full code snapshots (too large)
      // Store last 20 entries with full snapshots, older ones are summary-only
      const toSave = this.entries.slice(-20);
      localStorage.setItem(this.storageKey, JSON.stringify(toSave));
    } catch (e) {
      console.warn("Failed to save edit history to localStorage:", e);
    }
  }

  pushEdit(entry: EditHistoryEntry): void {
    this.entries.push(entry);
    // Trim to MAX_HISTORY
    if (this.entries.length > MAX_HISTORY) {
      this.entries = this.entries.slice(-MAX_HISTORY);
    }
    this.saveToStorage();
  }

  /**
   * Force-revert an AI edit by restoring the document to codeBeforeEdit.
   * Returns the code to restore, or null if the entry is not found.
   */
  revertEdit(id: string): string | null {
    const entry = this.entries.find((e) => e.id === id);
    if (!entry || entry.isReverted) return null;

    entry.isReverted = true;
    this.saveToStorage();
    return entry.codeBeforeEdit;
  }

  /**
   * Reapply a previously reverted AI edit by restoring codeAfterEdit.
   * Returns the code to apply, or null if the entry is not found or not reverted.
   */
  reapplyEdit(id: string): string | null {
    const entry = this.entries.find((e) => e.id === id);
    if (!entry || !entry.isReverted) return null;

    entry.isReverted = false;
    this.saveToStorage();
    return entry.codeAfterEdit;
  }

  getEntry(id: string): EditHistoryEntry | undefined {
    return this.entries.find((e) => e.id === id);
  }

  getEntryByMessageId(messageId: string): EditHistoryEntry | undefined {
    return this.entries.find((e) => e.messageId === messageId);
  }

  getHistory(): EditHistoryEntry[] {
    return [...this.entries];
  }

  isReverted(id: string): boolean {
    const entry = this.entries.find((e) => e.id === id);
    return entry?.isReverted ?? false;
  }

  clear(): void {
    this.entries = [];
    try {
      localStorage.removeItem(this.storageKey);
    } catch (_) {}
  }
}
