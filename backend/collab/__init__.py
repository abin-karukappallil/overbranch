"""
backend/collab — Realtime collaborative editing (Yjs CRDT over WebSocket)
=========================================================================
See COLLABORATION.md for the full architecture. In short:

    Monaco  <->  Y.Doc (browser)  <->  y-websocket  <->  /ws/collab/{project}
                                                              |
                                              CollabRoom (authoritative Y.Doc)
                                                              |
                                      debounced -> disk + Supabase latex_documents
                                                -> CRDT blob (restart safety)

Modules:
  config       COLLAB_* environment settings
  events       structured COLLAB_* logging
  access       project role resolution (reuses projects / project_members)
  tickets      one-time HMAC websocket admission tickets
  persistence  document text + CRDT state storage
  room         one room per project: protocol, seeding, presence, persistence
  manager      room registry, idle reaping, shutdown flush
"""

from .config import config
from .manager import room_manager, warn_if_multi_worker

__all__ = ["config", "room_manager", "warn_if_multi_worker"]
