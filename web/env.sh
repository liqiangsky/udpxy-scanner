#!/bin/sh
# ==========================================
# 运行时环境变量注入脚本
#
# 在 nginx 启动前，将 $VITE_BACKEND_URL 注入到
# index.html 的 __RUNTIME_ENV__ 占位符中，
# 实现 API 基址的运行时配置而非编译时写死。
#
# 用法:
#   docker run -e VITE_BACKEND_URL=http://host:7860 ...
#   不设环境变量则默认回退到 "/api"（走 nginx 反向代理）
# ==========================================

set -e

if [ -n "$VITE_BACKEND_URL" ]; then
  RUNTIME_ENV="{\"VITE_BACKEND_URL\":\"$VITE_BACKEND_URL\"}"
else
  RUNTIME_ENV="{}"
fi

sed "s|__RUNTIME_ENV__|$RUNTIME_ENV|g" /usr/share/nginx/html/index.html > /tmp/index.html
mv /tmp/index.html /usr/share/nginx/html/index.html

# VITE_BACKEND_URL: nginx 反向代理的后端地址，默认 docker compose 服务名
# 单独部署时通过 -e VITE_BACKEND_URL=http://host:port 覆盖
VITE_BACKEND_URL="${VITE_BACKEND_URL:-http://backend:7860}"
sed "s|__VITE_BACKEND_URL__|$VITE_BACKEND_URL|g" /etc/nginx/nginx.conf > /tmp/nginx.conf
mv /tmp/nginx.conf /etc/nginx/nginx.conf

exec nginx -g "daemon off;"
