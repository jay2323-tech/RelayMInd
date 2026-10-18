from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from relaymind.api.auth import router as auth_router
from relaymind.api.deps import current_principal
from relaymind.api.health import router
from relaymind.api.platform import router as platform_router
from relaymind.api.runs import router as runs_router
from relaymind.api.workflow import router as workflow_router
from relaymind.platform.identity import Principal

load_dotenv()

app = FastAPI(title="RelayMind", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(platform_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(workflow_router, prefix="/api")


@app.on_event("startup")
def _maybe_start_reminder_worker():
    # Optional in-process worker for local demos (RELAYMIND_REMINDER_WORKER=1). Otherwise run
    # scripts/reminder_worker.py as its own process. Claims make several workers safe.
    import os
    import threading
    if os.getenv("RELAYMIND_REMINDER_WORKER") == "1":
        from relaymind.api.deps import get_client
        from relaymind.workflow.reminders import worker_loop
        threading.Thread(target=worker_loop, args=(get_client(),), daemon=True, name="reminder-worker").start()


@app.get("/api/identity")
def identity(principal: Principal = Depends(current_principal)):
    # Authenticated local demo account (server-side session); not a production identity provider.
    return principal.public()


# ---------------------------------------------------------------- production: serve the built frontend
def mount_frontend(target, static_dir):
    """Serve the built UI from the same origin as /api. Registered LAST so every /api route wins; unknown
    non-API paths fall back to index.html (SPA routing); files outside static_dir are never served."""
    from pathlib import Path
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    root = Path(static_dir).resolve() if static_dir else None
    if root is None or not (root / "index.html").is_file():
        return False

    @target.get("/{full_path:path}", include_in_schema=False)
    def _frontend(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and root in candidate.parents:   # no path traversal
            return FileResponse(candidate)
        return FileResponse(root / "index.html")
    return True


import os as _os

mount_frontend(app, _os.getenv("RELAYMIND_STATIC_DIR"))
