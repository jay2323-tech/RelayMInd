from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from relaymind.api.health import router

app = FastAPI(title="RelayMind", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)
app.include_router(router, prefix="/api")
