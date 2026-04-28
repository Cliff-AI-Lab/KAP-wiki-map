# KAP 后端 + 前端一体化构建
# 镜像标签：kap/backend:v1.0.0-m0

# ── Stage 1: 前端构建 ──
FROM node:20-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: 后端运行 ──
FROM python:3.11-slim

LABEL org.opencontainers.image.title="KAP Backend" \
      org.opencontainers.image.description="KAP 知识智能体平台 · 后端" \
      org.opencontainers.image.version="v1.0.0-m0" \
      org.opencontainers.image.source="https://github.com/kap"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

# 将前端构建产物放入 frontend/dist
COPY --from=frontend-build /frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
