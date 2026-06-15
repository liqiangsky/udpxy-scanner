# ==========================================
# 后端 Dockerfile — HF Spaces 部署 / 独立运行
# 构建: docker build -t udpxy-backend .
# 运行: docker run -p 7860:7860 udpxy-backend
# ==========================================
FROM python:3.11-slim-bookworm

WORKDIR /app

# 安装运行时工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝后端代码
COPY . /app/server/

ENV PYTHONPATH=/app/server
ENV PYTHONUNBUFFERED=1

# 数据目录
ENV DB_PATH=/app/data/udpxy_scanner.db
ENV CACHE_DB_PATH=/app/data/source_cache.db
ENV IPTV_DB_PATH=/app/data/iptv_list.db

RUN mkdir -p /app/data

# HF Spaces 默认端口 7860
EXPOSE 7860

# 启动 uvicorn
CMD uvicorn main:app --host 0.0.0.0 --port 7860
