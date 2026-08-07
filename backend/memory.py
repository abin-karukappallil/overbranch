"""
memory.py — Conversation & Project Memory

Stores per-project conversation history and project metadata in-memory.
Provides context strings for the prompt builder.
"""
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from collections import OrderedDict

logger = logging.getLogger("memory")

MAX_TURNS = 10
FULL_TURNS_KEPT = 4
MAX_PROJECTS = 50  # LRU cap


class ConversationMemory:
    """In-memory conversation store, keyed by project_id. LRU eviction."""

    def __init__(self):
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def _ensure_project(self, project_id: str) -> Dict[str, Any]:
        if project_id not in self._store:
            self._store[project_id] = {
                "turns": [],
                "recent_files": [],
                "recent_chunk_summaries": [],
            }
        # LRU: move to end
        self._store.move_to_end(project_id)
        # Evict oldest if over cap
        while len(self._store) > MAX_PROJECTS:
            self._store.popitem(last=False)
        return self._store[project_id]

    def add_turn(
        self,
        project_id: str,
        user_prompt: str,
        assistant_response: Dict[str, Any],
        file_path: str = "",
        chunk_summaries: Optional[List[str]] = None,
    ):
        """Record a conversation turn."""
        entry = self._ensure_project(project_id)

        entry["turns"].append({
            "role": "user",
            "content": user_prompt,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        entry["turns"].append({
            "role": "assistant",
            "content": assistant_response.get("explanation", ""),
            "proposed_chunk_len": len(assistant_response.get("proposed_chunk", "")),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Trim to MAX_TURNS (each turn = 2 entries)
        if len(entry["turns"]) > MAX_TURNS * 2:
            entry["turns"] = entry["turns"][-(MAX_TURNS * 2):]

        # Track recent files
        if file_path and file_path not in entry["recent_files"]:
            entry["recent_files"].append(file_path)
            entry["recent_files"] = entry["recent_files"][-5:]

        # Track recent chunk summaries
        if chunk_summaries:
            entry["recent_chunk_summaries"] = chunk_summaries[-5:]

    def get_conversation_context(self, project_id: str) -> str:
        """Build a conversation context string for the prompt builder."""
        if project_id not in self._store:
            return ""

        entry = self._store[project_id]
        turns = entry["turns"]
        if not turns:
            return ""

        lines = []

        # Older turns: summarize to 1-line each
        older = turns[:-(FULL_TURNS_KEPT * 2)] if len(turns) > FULL_TURNS_KEPT * 2 else []
        for t in older:
            role = t["role"].upper()
            content = t["content"][:80].replace("\n", " ")
            lines.append(f"[{role}] {content}...")

        # Recent turns: full content
        recent = turns[-(FULL_TURNS_KEPT * 2):]
        for t in recent:
            role = t["role"].upper()
            content = t["content"][:300].replace("\n", " ")
            lines.append(f"[{role}] {content}")

        if entry.get("recent_files"):
            lines.append(f"[RECENT FILES] {', '.join(entry['recent_files'])}")

        return "\n".join(lines)

    def get_recent_chunk_summaries(self, project_id: str) -> List[str]:
        """Return recent chunk summaries for diversity checking."""
        if project_id not in self._store:
            return []
        return self._store[project_id].get("recent_chunk_summaries", [])


class ProjectMemory:
    """In-memory project metadata store, lazily populated from preamble scanning."""

    def __init__(self):
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def scan_and_store(self, project_id: str, tex_content: str):
        """Scan LaTeX preamble and extract project metadata."""
        meta: Dict[str, Any] = {
            "document_class": "",
            "packages": [],
            "title": "",
            "authors": [],
            "structure": [],
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

        # Document class
        dc_match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", tex_content)
        if dc_match:
            meta["document_class"] = dc_match.group(1)

        # Packages
        for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", tex_content):
            pkgs = [p.strip() for p in m.group(1).split(",")]
            meta["packages"].extend(pkgs)
        meta["packages"] = list(dict.fromkeys(meta["packages"]))  # dedupe preserving order

        # Title
        title_match = re.search(r"\\title\{([^}]+)\}", tex_content)
        if title_match:
            meta["title"] = title_match.group(1)

        # Authors
        for m in re.finditer(r"\\author\{([^}]+)\}", tex_content):
            meta["authors"].append(m.group(1).strip())

        # Structure (sections)
        for m in re.finditer(r"\\section\{([^}]+)\}", tex_content):
            meta["structure"].append(f"section:{m.group(1)}")
        for m in re.finditer(r"\\subsection\{([^}]+)\}", tex_content):
            meta["structure"].append(f"subsection:{m.group(1)}")

        self._store[project_id] = meta
        self._store.move_to_end(project_id)
        while len(self._store) > MAX_PROJECTS:
            self._store.popitem(last=False)

        logger.info(f"Project memory scanned for '{project_id}': "
                     f"class={meta['document_class']}, {len(meta['packages'])} packages, "
                     f"{len(meta['structure'])} structural elements")

    def get_project_context(self, project_id: str) -> str:
        """Build a project context string for the prompt builder."""
        if project_id not in self._store:
            return ""

        meta = self._store[project_id]
        lines = []

        if meta["document_class"]:
            lines.append(f"Document class: {meta['document_class']}")
        if meta["title"]:
            lines.append(f"Title: {meta['title']}")
        if meta["authors"]:
            lines.append(f"Authors: {', '.join(meta['authors'])}")
        if meta["packages"]:
            lines.append(f"Packages: {', '.join(meta['packages'][:15])}")
        if meta["structure"]:
            lines.append(f"Structure: {' → '.join(meta['structure'][:10])}")

        return "\n".join(lines)

    def is_scanned(self, project_id: str) -> bool:
        return project_id in self._store


# Module-level singletons
conversation_memory = ConversationMemory()
project_memory = ProjectMemory()
