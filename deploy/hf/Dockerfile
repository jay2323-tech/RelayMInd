# RelayMind for a FREE Hugging Face Docker Space: FalkorDB + backend + built UI in ONE container.
# FalkorDB listens only on 127.0.0.1 inside the container (never exposed) with a random per-start password.
# Data lives in the container: a restart reloads the demo companies (testers' work is not kept). See docs/deploy-free.md.

FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Same pinned FalkorDB image as compose.yaml (Debian 13): provides redis-server + the falkordb module.
FROM falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv passwd \
    && rm -rf /var/lib/apt/lists/*
# Hugging Face runs containers as uid 1000.
RUN useradd --create-home --uid 1000 user
ENV HOME=/home/user PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PORT=7860 \
    RELAYMIND_STATIC_DIR=/app/frontend_dist \
    RELAYMIND_COOKIE_SECURE=1 \
    RELAYMIND_REMINDER_WORKER=1 \
    RELAYMIND_PUBLIC_DEMO=1 \
    AGENT_PROVIDER=gemini GEMINI_MODEL=gemini-3.5-flash-lite \
    AGENT_FALLBACK_PROVIDER=groq GROQ_MODEL=openai/gpt-oss-120b
WORKDIR /app
COPY backend/ ./backend/
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -e ./backend
COPY scripts/ ./scripts/
COPY fixtures/ ./fixtures/
COPY deploy/hf/start.sh ./start.sh
COPY --from=frontend /build/dist ./frontend_dist
RUN chown -R user /app && chmod +x /app/start.sh
USER user
EXPOSE 7860
ENTRYPOINT ["/app/start.sh"]
