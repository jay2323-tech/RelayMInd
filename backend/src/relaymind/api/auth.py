"""Login / logout / current account. Local demo authentication (see platform/identity.py)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field

from relaymind.api.deps import current_principal
from relaymind.contracts.models import StrictModel
from relaymind.platform.identity import (
    SESSION_COOKIE, SESSION_TTL_SECONDS, AuthError, Principal, login as do_login, logout as do_logout,
)

router = APIRouter(prefix="/auth")


class LoginBody(StrictModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL_SECONDS, httponly=True, samesite="strict",
                        secure=os.getenv("RELAYMIND_COOKIE_SECURE") == "1", path="/api")


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    do_logout(request.cookies.get(SESSION_COOKIE))  # switching accounts never keeps the old session
    try:
        token, principal = do_login(body.username, body.password)
    except AuthError as exc:
        raise HTTPException(401, str(exc)) from None
    _set_cookie(response, token)
    return principal.public()


@router.post("/logout")
def logout(request: Request, response: Response):
    do_logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/api")
    return {"signed_out": True}


@router.get("/me")
def me(principal: Principal = Depends(current_principal)):
    return principal.public()
