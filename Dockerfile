# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app

COPY web/package*.json ./web/
RUN cd web && npm ci

COPY web/ ./web/
RUN cd web && npm run build

# Stage 2: Backend
FROM python:3.10-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY --from=frontend-build /app/web/dist ./web/dist

ARG DOWNLOAD_MODELS=0
RUN if [ "$DOWNLOAD_MODELS" = "1" ]; then \
      python -c "from server.util.CaptchaUtils import ensure_model_exists, MODEL_URLS; [ensure_model_exists(k,v) for k,v in MODEL_URLS.items()]" ; \
    fi

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
