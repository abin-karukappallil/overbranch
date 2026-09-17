"""
backend/opencode/ — OpenCode-Style Agentic Pipeline
=====================================================
Replaces the RAG-based chunker/retriever pipeline with an in-memory
shadow-buffer agent that uses exact-match tools (Read, Grep, Replace),
verifies edits via shadow compilation, and produces strict diffs for
the frontend InlineDiffEditor.
"""

from .shadow_workspace import ShadowWorkspace
from .agent_loop import stream_opencode_agent, run_opencode_agent

__all__ = [
    "ShadowWorkspace",
    "stream_opencode_agent",
    "run_opencode_agent",
]
