"""Local demo authentication and sessions (no database)."""
import pytest

from relaymind.platform import identity as idm


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("RELAYMIND_DEMO_PASSWORD", "correct horse")
    idm.reset_for_tests()
    yield
    idm.reset_for_tests()


def test_login_resolves_server_owned_membership():
    token, p = idm.login("Northstar.Lead", "correct horse")
    assert (p.tenant_id, p.user_id, p.company_id, p.projects) == ("demo-a", "developer-a", "northstar", frozenset({"launch-01"}))
    assert idm.resolve(token) == p
    assert len(token) >= 40


def test_unknown_user_and_wrong_password_give_the_same_error():
    with pytest.raises(idm.AuthError, match="Invalid username or password") as a:
        idm.login("nobody", "correct horse")
    with pytest.raises(idm.AuthError, match="Invalid username or password") as b:
        idm.login("northstar.lead", "wrong")
    assert str(a.value) == str(b.value)


def test_lockout_after_repeated_failures():
    for _ in range(5):
        with pytest.raises(idm.AuthError):
            idm.login("harbor.lead", "wrong", now=1000.0)
    with pytest.raises(idm.AuthError, match="Too many"):
        idm.login("harbor.lead", "correct horse", now=1001.0)
    assert idm.login("harbor.lead", "correct horse", now=1100.0)[1].company_id == "harbor"


def test_expiry_and_logout():
    token, _ = idm.login("northstar.lead", "correct horse", now=0.0)
    with pytest.raises(idm.AuthError, match="expired"):
        idm.resolve(token, now=idm.SESSION_TTL_SECONDS + 1)
    token, _ = idm.login("northstar.lead", "correct horse")
    idm.logout(token)
    with pytest.raises(idm.AuthError):
        idm.resolve(token)
    with pytest.raises(idm.AuthError):
        idm.resolve(None)


def test_login_disabled_without_configured_password(monkeypatch):
    monkeypatch.delenv("RELAYMIND_DEMO_PASSWORD")
    idm.reset_for_tests()
    with pytest.raises(idm.AuthError, match="disabled"):
        idm.login("northstar.lead", "")


def test_plain_password_and_raw_tokens_are_not_stored():
    token, _ = idm.login("northstar.lead", "correct horse")
    assert token not in idm._sessions and all(len(k) == 64 for k in idm._sessions)
    salt, digest = idm._password_record
    assert b"correct horse" not in salt + digest
