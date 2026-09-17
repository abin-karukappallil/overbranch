"""
cancellation.py — Thread-safe Cancellation & Resource Abort System

Provides CancellationToken and CancellationManager to immediately halt
in-flight AI generation, close streaming HTTP connections to LLM providers
(Gemini Web2API, OpenRouter), and stop section loops / auto-repairs
when the user stops the response or disconnects.
"""

import logging
import threading
from typing import Optional, Set, Dict, Any, List

logger = logging.getLogger("cancellation")


class LLMOperationCancelled(Exception):
    """Raised when an AI operation is stopped by the user or client disconnect."""
    def __init__(self, message: str = "AI operation stopped by user."):
        super().__init__(message)
        self.message = message


class CancellationToken:
    """
    Thread-safe cancellation token.
    Can be checked by background tasks, thread pool executors, and provider streams.
    Tracks active network resources (e.g. streaming HTTP responses) and forcefully
    closes them upon cancellation.
    """

    def __init__(self, request_id: str, project_id: Optional[str] = None):
        self.request_id = request_id
        self.project_id = project_id
        self._is_cancelled = False
        self._cancel_reason = ""
        self._lock = threading.Lock()
        self._resources: Set[Any] = set()

    def is_cancelled(self) -> bool:
        """Non-blocking check if cancellation has been requested."""
        with self._lock:
            return self._is_cancelled

    def check_cancelled(self):
        """Raises LLMOperationCancelled immediately if cancelled."""
        with self._lock:
            if self._is_cancelled:
                raise LLMOperationCancelled(self._cancel_reason or "AI operation stopped by user.")

    def cancel(self, reason: str = "Stopped by user"):
        """
        Marks the token as cancelled and forcefully closes all registered
        network streams/sockets (e.g. OpenAI SDK stream, requests.Response).
        """
        resources_to_close: List[Any] = []
        with self._lock:
            if self._is_cancelled:
                return
            self._is_cancelled = True
            self._cancel_reason = reason
            resources_to_close = list(self._resources)
            self._resources.clear()

        logger.info(f"Cancellation requested for request_id='{self.request_id}' (reason: {reason})")

        # Close registered network sockets / streams outside lock to avoid deadlocks
        for res in resources_to_close:
            try:
                if hasattr(res, "close") and callable(res.close):
                    res.close()
                elif hasattr(res, "response") and hasattr(res.response, "close"):
                    res.response.close()
            except Exception as e:
                logger.debug(f"Error closing resource during cancel for {self.request_id}: {e}")

    def register_resource(self, res: Any):
        """
        Registers a stream or socket to be closed if cancelled.
        If already cancelled, closes it immediately.
        """
        if res is None:
            return

        should_close_immediately = False
        with self._lock:
            if self._is_cancelled:
                should_close_immediately = True
            else:
                self._resources.add(res)

        if should_close_immediately:
            try:
                if hasattr(res, "close") and callable(res.close):
                    res.close()
            except Exception:
                pass

    def unregister_resource(self, res: Any):
        """Safely removes a resource once completed normally."""
        if res is None:
            return
        with self._lock:
            self._resources.discard(res)


class CancellationManager:
    """
    Registry for active CancellationTokens.
    Allows looking up and cancelling tokens by request_id or project_id.
    """

    def __init__(self):
        self._tokens_by_req: Dict[str, CancellationToken] = {}
        self._lock = threading.Lock()

    def create_token(self, request_id: str, project_id: Optional[str] = None) -> CancellationToken:
        """Creates and registers a new CancellationToken."""
        token = CancellationToken(request_id=request_id, project_id=project_id)
        with self._lock:
            self._tokens_by_req[request_id] = token
        return token

    def get_token(self, request_id: str) -> Optional[CancellationToken]:
        """Retrieves a token by request_id."""
        with self._lock:
            return self._tokens_by_req.get(request_id)

    def cancel(
        self,
        request_id: Optional[str] = None,
        project_id: Optional[str] = None,
        reason: str = "Stopped by user",
    ) -> bool:
        """
        Cancels active tokens matching request_id and/or project_id.
        Returns True if at least one active token was cancelled.
        """
        matched_tokens: List[CancellationToken] = []
        with self._lock:
            for token in self._tokens_by_req.values():
                match = False
                if request_id and token.request_id == request_id:
                    match = True
                elif project_id and token.project_id == project_id:
                    match = True
                if match:
                    matched_tokens.append(token)

        for token in matched_tokens:
            token.cancel(reason=reason)

        return len(matched_tokens) > 0

    def cleanup(self, request_id: str):
        """Removes a token from the registry when request finishes."""
        with self._lock:
            self._tokens_by_req.pop(request_id, None)

    def active_count(self) -> int:
        """Returns number of active tracked tokens."""
        with self._lock:
            return len(self._tokens_by_req)


# Global singleton instance
cancellation_manager = CancellationManager()
