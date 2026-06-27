FROM python:3.10-slim

# Non-root user — reduces attack surface in production containers.
RUN useradd --create-home --shell /bin/bash --uid 1001 appuser

WORKDIR /app/backend

# Install Python dependencies first (cached layer — only rebuilt when
# requirements.txt changes).
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY backend/ .

# Scenario JSON files.  config.py resolves parents[2]/scenarios → /app/scenarios.
COPY scenarios/ /app/scenarios/

# Persistent data directory for SQLite.  Owned by the non-root user so the
# process can write the database file without elevated privileges.
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# PORT is injected at runtime by Railway (and other PaaS platforms).
# Falls back to 8000 for docker-compose and plain Docker usage.
#
# --proxy-headers          trust X-Forwarded-* headers from Railway's reverse proxy
# --forwarded-allow-ips=*  accept forwarded headers from any upstream IP
# --log-level info         structured JSON logs (StructuredFormatter in main.py)
#
# Single worker is intentional: the session store is in-process memory.
# Multiple workers would create separate session namespaces and break WebSockets.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --log-level info"]
