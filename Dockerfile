# RelayMind production image: builds the frontend, then runs the backend which also serves it.
# One service, one URL: the UI calls /api on the same origin, so no CORS and first-party cookies.

# ---- 1. build the frontend (static files) ----
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. backend runtime ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    RELAYMIND_STATIC_DIR=/app/frontend_dist \
    RELAYMIND_COOKIE_SECURE=1 \
    RELAYMIND_REMINDER_WORKER=1
WORKDIR /app
COPY backend/ ./backend/
# Editable install keeps the package at /app/backend/src so fixture paths (relative to the code) resolve.
RUN pip install --no-cache-dir -e ./backend
COPY scripts/ ./scripts/
COPY fixtures/ ./fixtures/
COPY --from=frontend /build/dist ./frontend_dist
# Non-root user
RUN useradd --create-home relaymind && chown -R relaymind /app
USER relaymind
EXPOSE 8000
CMD ["python", "scripts/prod_start.py"]
