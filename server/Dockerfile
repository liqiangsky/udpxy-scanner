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
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝后端代码（含本地 xdb 文件，如有）
COPY . /app/server/

# 下载 ip2region 离线数据库（本地已有则覆盖，确保最新）
RUN mkdir -p /app/server/data && \
    curl -fSL -o /app/server/data/ip2region_v4.xdb \
    "https://raw.githubusercontent.com/lionsoul2014/ip2region/master/data/ip2region_v4.xdb" || \
    echo "⚠️ curl 下载 xdb 失败，使用 COPY 的本地文件（如有）"

ENV PYTHONPATH=/app/server
ENV PYTHONUNBUFFERED=1

# 数据目录
ENV DB_PATH=/app/data/data.db

RUN mkdir -p /app/data

# entrypoint（已包含在 server/scripts/ 中自动迁移）
RUN chmod +x /app/server/scripts/entrypoint.sh

# HF Spaces 默认端口 7860
EXPOSE 7860

ENTRYPOINT ["/app/server/scripts/entrypoint.sh"]
