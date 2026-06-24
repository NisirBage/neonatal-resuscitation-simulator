# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:18-alpine AS builder

WORKDIR /app

# Install dependencies (package-lock.json used when present for reproducibility)
COPY frontend/package*.json ./
RUN npm install

# Copy source and build
COPY frontend/ .

# Vite environment variables are baked in at build time.
# Pass the backend address as build args:
#   docker build --build-arg VITE_API_BASE_URL=http://myserver:8000 ...
# docker-compose passes these from the .env file automatically.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_WS_BASE_URL=ws://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL

RUN npm run build

# ── Stage 2: serve ───────────────────────────────────────────────────────────
FROM nginx:stable-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Exposed internally on port 80; docker-compose maps this to host port 5173.
EXPOSE 80
