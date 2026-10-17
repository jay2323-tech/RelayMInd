from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from relaymind.api.health import router
from relaymind.api.platform import router as platform_router
from relaymind.api.runs import router as runs_router
from relaymind.api.deps import trusted_context

load_dotenv()

app = FastAPI(title="RelayMind", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router, prefix="/api")
app.include_router(platform_router, prefix="/api")
app.include_router(runs_router, prefix="/api")


@app.get("/api/identity")
def identity():
    # Local demo identity from server configuration; not production authentication.
    ctx = trusted_context()
    return {"tenant_id": ctx.tenant_id, "user_id": ctx.user_id, "mode": "local-demo-identity"}
