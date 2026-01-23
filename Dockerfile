# Stage 1: Build Frontend
FROM node:18-bookworm-slim AS frontend-build
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Stage 2: Backend
FROM python:3.10-slim
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY --from=frontend-build /app/web/dist ./web/dist

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
