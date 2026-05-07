# ── Stage 1: Build frontend ──
FROM node:20-slim AS frontend
WORKDIR /app/web
COPY app/web/package.json app/web/package-lock.json* ./
RUN npm ci
COPY app/web/ ./
RUN npm run build

# ── Stage 2: Python runtime ──
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY app/service/ app/service/
COPY data/ data/

COPY --from=frontend /app/web/dist app/web/dist

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.service.api:app", "--host", "0.0.0.0", "--port", "8000"]
