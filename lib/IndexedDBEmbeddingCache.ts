/**
 * IndexedDBEmbeddingCache.ts — Client-Side Document & Chunk Cache
 *
 * Uses IndexedDB to cache document chunks and semantic retrieval results
 * locally in the browser, achieving <100ms retrieval and offline resilience.
 */

const DB_NAME = "overbranch_embedding_cache_db";
const DB_VERSION = 1;
const STORE_NAME = "chunks_cache";

export interface CachedChunkEntry {
  cacheKey: string;      // `${projectId}_${filePath}_${fileHash}`
  projectId: string;
  filePath: string;
  fileHash: string;
  timestamp: number;
  chunks: Array<{
    chunk_index: number;
    chunk_type: string;
    content: string;
    section?: string;
    start_line?: number;
    end_line?: number;
    summary?: string;
  }>;
}

let dbInstancePromise: Promise<IDBDatabase> | null = null;

function getDB(): Promise<IDBDatabase> {
  if (typeof window === "undefined" || !("indexedDB" in window)) {
    return Promise.reject(new Error("IndexedDB is not supported in this environment"));
  }

  if (!dbInstancePromise) {
    dbInstancePromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: "cacheKey" });
          store.createIndex("projectId", "projectId", { unique: false });
          store.createIndex("timestamp", "timestamp", { unique: false });
        }
      };

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  return dbInstancePromise;
}

/**
 * Fast SHA-256 or djb2 hash for text content fingerprinting
 */
export function computeContentHash(content: string): string {
  let hash = 5381;
  for (let i = 0; i < content.length; i++) {
    hash = (hash * 33) ^ content.charCodeAt(i);
  }
  return (hash >>> 0).toString(16);
}

/**
 * Retrieves cached chunks from IndexedDB if content hash matches
 */
export async function getCachedDocumentChunks(
  projectId: string,
  filePath: string,
  fileHash: string
): Promise<CachedChunkEntry["chunks"] | null> {
  try {
    const db = await getDB();
    const cacheKey = `${projectId}_${filePath}_${fileHash}`;

    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const store = tx.objectStore(STORE_NAME);
      const request = store.get(cacheKey);

      request.onsuccess = () => {
        const result = request.result as CachedChunkEntry | undefined;
        if (result && result.chunks) {
          resolve(result.chunks);
        } else {
          resolve(null);
        }
      };

      request.onerror = () => resolve(null);
    });
  } catch (_) {
    return null;
  }
}

/**
 * Stores document chunks in IndexedDB
 */
export async function setCachedDocumentChunks(
  projectId: string,
  filePath: string,
  fileHash: string,
  chunks: CachedChunkEntry["chunks"]
): Promise<void> {
  try {
    const db = await getDB();
    const cacheKey = `${projectId}_${filePath}_${fileHash}`;

    const entry: CachedChunkEntry = {
      cacheKey,
      projectId,
      filePath,
      fileHash,
      timestamp: Date.now(),
      chunks,
    };

    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      store.put(entry);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch (_) {}
}

/**
 * Clears old or specific project cache from IndexedDB
 */
export async function clearProjectEmbeddingCache(projectId: string): Promise<void> {
  try {
    const db = await getDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      const index = store.index("projectId");
      const request = index.getAllKeys(projectId);

      request.onsuccess = () => {
        const keys = request.result;
        keys.forEach((k) => store.delete(k));
        resolve();
      };
      request.onerror = () => resolve();
    });
  } catch (_) {}
}
