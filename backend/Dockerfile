FROM python:3.10-slim

WORKDIR /app/backend

# Install dependencies first (cached layer)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Copy scenario definitions alongside backend so Path(__file__).parents[2]/scenarios resolves
# config.py is at /app/backend/app/config.py → parents[2] = /app → /app/scenarios
COPY scenarios/ /app/scenarios/

# Persistent data directory for SQLite database
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
