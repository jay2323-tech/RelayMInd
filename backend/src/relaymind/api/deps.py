"""Shared API dependencies: authenticated principal, membership checks, client, errors.

Identity comes only from the server-side session (relaymind.platform.identity). Request
bodies never carry tenant, company, user or graph fields (strict models reject them).
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request

from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.graph.connection import create_client
from relaymind.platform.identity import SESSION_COOKIE, AuthError, Principal, resolve

_client = None
_client_lock = threading.Lock()


def get_client():
    global _client
    with _client_lock:
        if _client is None:
            _client = create_client()
        return _client


def current_principal(request: Request) -> Principal:
    try:
        return resolve(request.cookies.get(SESSION_COOKIE))
    except AuthError as exc:
        raise HTTPException(401, str(exc)) from None


def project_member(project_id: str, principal: Principal = Depends(current_principal)) -> Principal:
    """Authenticated AND a member of this project in the server's registry and graph map."""
    if project_id not in principal.projects:
        raise HTTPException(404, "Not found or access denied")
    try:
        authorized_graph(get_client(), principal.context(), project_id)
    except AccessDenied:
        raise HTTPException(404, "Not found or access denied") from None
    return principal


@contextmanager
def api_errors():
    """Map domain errors to HTTP without leaking whether private records exist."""
    from relaymind.memory.artifacts import ArtifactConflict
    from relaymind.memory.decisions import DecisionMemoryError
    from relaymind.memory.manufacturing import ManufacturingError
    from relaymind.memory.tasks import TaskMemoryError
    from relaymind.services.actions import ActionError
    from relaymind.workflow.plan_reviews import PlanReviewConflict
    try:
        yield
    except AccessDenied:
        raise HTTPException(404, "Not found or access denied") from None
    except (ActionError, ArtifactConflict, DecisionMemoryError, ManufacturingError, TaskMemoryError,
            PlanReviewConflict) as exc:
        raise HTTPException(409, f"{type(exc).__name__}: {exc}") from None
    except (ValueError, LookupError) as exc:
        raise HTTPException(422, f"{type(exc).__name__}: {exc}") from None
