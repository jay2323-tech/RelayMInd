"""Production same-origin frontend serving (no database)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from relaymind.main import mount_frontend


def make(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>RelayMind UI</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not serve", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}
    assert mount_frontend(app, str(dist)) is True
    return TestClient(app)


def test_ui_assets_spa_fallback_and_api_precedence(tmp_path):
    c = make(tmp_path)
    assert c.get("/").text == "<html>RelayMind UI</html>"
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/some/deep/route").text == "<html>RelayMind UI</html>"      # SPA fallback
    assert c.get("/api/health").json() == {"status": "ok"}                     # API wins
    assert c.get("/api/does-not-exist").status_code == 404                     # never the UI for /api


def test_no_path_traversal(tmp_path):
    c = make(tmp_path)
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert "do not serve" not in c.get(path).text, path


def test_disabled_without_a_build(tmp_path):
    assert mount_frontend(FastAPI(), None) is False
    assert mount_frontend(FastAPI(), str(tmp_path / "missing")) is False
