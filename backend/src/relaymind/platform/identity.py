"""Local authentication, server-side sessions and company/project membership (P2-01/P2-02).

Scope and limits (be precise when describing this):
- Synthetic demo accounts only. The membership registry below is server-owned code; the
  browser and the model never choose tenant, company, graph or project access.
- One shared demo password is read from the server environment (RELAYMIND_DEMO_PASSWORD).
  It is hashed with PBKDF2-HMAC-SHA256 and a random salt at first use; the plain value is
  never stored or logged. Unset password -> login is disabled (fail closed).
- Sessions are random 256-bit tokens kept server-side (only their SHA-256 is stored), sent in
  an HttpOnly, SameSite=Strict cookie, with absolute expiry and explicit logout.
- In-memory session store and login throttling: valid for ONE backend process. A restart logs
  everyone out. This is local demo authentication, not a production identity provider.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass

from relaymind.contracts.models import TrustedContext

SESSION_COOKIE = "relaymind_session"
SESSION_TTL_SECONDS = int(os.getenv("RELAYMIND_SESSION_TTL", str(8 * 3600)))
_PBKDF2_ROUNDS = 310_000
_MAX_FAILURES, _LOCKOUT_SECONDS = 5, 30


@dataclass(frozen=True)
class Account:
    username: str
    user_id: str
    tenant_id: str
    company_id: str
    display_name: str
    projects: frozenset[str]


# Server-owned membership registry. Each tenant graph holds exactly one company.
ACCOUNTS: dict[str, Account] = {a.username: a for a in (
    Account("northstar.lead", "developer-a", "demo-a", "northstar", "Northstar launch lead", frozenset({"launch-01"})),
    Account("northstar.peer", "developer-a2", "demo-a", "northstar", "Northstar engineer", frozenset({"launch-01"})),
    Account("harbor.lead", "developer-b", "demo-b", "harbor", "Harbor operations lead", frozenset({"hb-route-07"})),
    Account("aw.quality", "aw-analyst", "adventureworks", "adventureworks", "AdventureWorks quality analyst",
            frozenset({"aw-qh-17"})),
)}


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, resolved by the server on every request."""
    username: str
    user_id: str
    tenant_id: str
    company_id: str
    display_name: str
    projects: frozenset[str]

    def context(self) -> TrustedContext:
        return TrustedContext(tenant_id=self.tenant_id, user_id=self.user_id)

    def public(self) -> dict:
        return {"username": self.username, "user_id": self.user_id, "tenant_id": self.tenant_id,
                "company_id": self.company_id, "display_name": self.display_name,
                "projects": sorted(self.projects), "mode": "local-demo-auth"}


class AuthError(Exception):
    """Login failed or the session is missing/expired. Message is safe to show."""


_lock = threading.Lock()
_sessions: dict[str, tuple[str, float]] = {}       # sha256(token) -> (username, expires_at)
_failures: dict[str, tuple[int, float]] = {}       # username -> (count, locked_until)
_password_record: tuple[bytes, bytes] | None = None
_password_source: str | None = None


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)


def _expected_password() -> tuple[bytes, bytes] | None:
    """Hash the configured demo password once (re-hash if the environment value changes)."""
    global _password_record, _password_source
    configured = os.getenv("RELAYMIND_DEMO_PASSWORD") or None
    if configured is None:
        return None
    fingerprint = hashlib.sha256(configured.encode()).hexdigest()
    if _password_record is None or _password_source != fingerprint:
        salt = secrets.token_bytes(16)
        _password_record, _password_source = (salt, _hash(configured, salt)), fingerprint
    return _password_record


def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(username: str, password: str, now: float | None = None) -> tuple[str, Principal]:
    """Return (session token, principal). Same error for unknown user and wrong password."""
    now = time.time() if now is None else now
    username = username.strip().lower()
    with _lock:
        count, locked_until = _failures.get(username, (0, 0.0))
        if locked_until > now:
            raise AuthError("Too many failed attempts. Try again shortly.")
        record = _expected_password()
        account = ACCOUNTS.get(username)
        ok = False
        if record is not None:
            salt, digest = record
            ok = hmac.compare_digest(_hash(password, salt), digest) and account is not None
        if record is None:
            raise AuthError("Login is disabled: the server has no demo password configured.")
        if not ok:
            count += 1
            _failures[username] = (0, now + _LOCKOUT_SECONDS) if count >= _MAX_FAILURES else (count, 0.0)
            raise AuthError("Invalid username or password.")
        _failures.pop(username, None)
        token = secrets.token_urlsafe(32)
        _sessions[_token_key(token)] = (username, now + SESSION_TTL_SECONDS)
    return token, principal_for(account)


def principal_for(account: Account) -> Principal:
    return Principal(account.username, account.user_id, account.tenant_id, account.company_id,
                     account.display_name, account.projects)


def resolve(token: str | None, now: float | None = None) -> Principal:
    if not token:
        raise AuthError("Sign in required.")
    now = time.time() if now is None else now
    with _lock:
        entry = _sessions.get(_token_key(token))
        if entry is None:
            raise AuthError("Sign in required.")
        username, expires_at = entry
        if expires_at <= now:
            _sessions.pop(_token_key(token), None)
            raise AuthError("Session expired. Sign in again.")
    account = ACCOUNTS.get(username)
    if account is None:  # account removed from the registry: session is void
        raise AuthError("Sign in required.")
    return principal_for(account)


def logout(token: str | None) -> None:
    if token:
        with _lock:
            _sessions.pop(_token_key(token), None)


def reset_for_tests() -> None:
    global _password_record, _password_source
    with _lock:
        _sessions.clear(); _failures.clear()
        _password_record = _password_source = None
