"""Shared API dependencies: trusted identity, database client, error mapping.

Identity is LOCAL DEMO scaffolding: the operator sets DEMO_TENANT_ID / DEMO_USER_ID in
the server's .env. The browser never supplies tenant, user or graph names. This is not
production authentication.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager

from fastapi import HTTPException

from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import AccessDenied
from relaymind.graph.connection import create_client

_client = None
_client_lock = threading.Lock()


def get_client():
    global _client
    with _client_lock:
        if _client is None:
            _client = create_client()
        return _client


def trusted_context() -> TrustedContext:
    return TrustedContext(tenant_id=os.getenv("DEMO_TENANT_ID", "demo-a"),
                          user_id=os.getenv("DEMO_USER_ID", "developer-a"))


@contextmanager
def api_errors():
    """Map domain errors to HTTP without leaking whether private records exist."""
    from relaymind.memory.artifacts import ArtifactConflict
    from relaymind.memory.decisions import DecisionMemoryError
    from relaymind.memory.tasks import TaskMemoryError
    from relaymind.services.actions import ActionError
    try:
        yield
    except AccessDenied:
        raise HTTPException(404, "Not found or access denied") from None
    except (ActionError, ArtifactConflict, DecisionMemoryError, TaskMemoryError) as exc:
        raise HTTPException(409, f"{type(exc).__name__}: {exc}") from None
    except (ValueError, LookupError) as exc:
        raise HTTPException(422, f"{type(exc).__name__}: {exc}") from None
