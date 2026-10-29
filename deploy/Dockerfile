# 绘梨衣 AI 陪伴后端 —— 生产镜像
#
# 构建：docker build -t erii-backend .
# 说明：生产环境通过反向代理（Caddy/Nginx）提供 HTTPS，
#       uvicorn 已启用 proxy_headers，会自动识别 X-Forwarded-Proto=https。

FROM python:3.12-slim

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 再拷贝源码
COPY backend/app ./app

# 数据与媒体目录（挂载持久化卷）
RUN mkdir -p /app/data /app/media

ENV LUMI_ENV=production \
    LUMI_HOST=0.0.0.0 \
    LUMI_PORT=8000 \
    LUMI_DB_PATH=/app/data/erii.db \
    LUMI_MEDIA_DIR=/app/media

EXPOSE 8000

# 生产环境用 uvicorn 直接起（不 reload）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
