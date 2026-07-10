#!/bin/sh
# ==========================================
# 运行时环境变量注入脚本
#
# 两个独立的环境变量，互不依赖：
#   VITE_BACKEND_URL  — JS 直连后端地址（注入 index.html 供前端读取）
#   NGINX_BACKEND_URL  — nginx 反代后端地址（替换 nginx.conf 占位符）
#
# 用法:
#   JS 直连: docker run -e VITE_BACKEND_URL=http://host:7860 ...
#   nginx反代: docker run -e NGINX_BACKEND_URL=http://host:7860 ...
#   不设环境变量则默认走 Docker Compose 内部反代（backend:7860）
# ==========================================

set -e

# ---------- VITE_BACKEND_URL ----------
# JS 直连模式下，注入到 index.html 中 window.__ENV__ 的 VITE_BACKEND_URL 字段
# 前端 shared.js 从中读取并拼上 /api 后缀
if [ -n "$VITE_BACKEND_URL" ]; then
  RUNTIME_ENV="{\"VITE_BACKEND_URL\":\"$VITE_BACKEND_URL\"}"
else
  RUNTIME_ENV="{}"
fi

sed "s|__RUNTIME_ENV__|$RUNTIME_ENV|g" /usr/share/nginx/html/index.html > /tmp/index.html
mv /tmp/index.html /usr/share/nginx/html/index.html

# ---------- NGINX_BACKEND_URL ----------
# nginx 反代模式下，替换 nginx.conf 中 __NGINX_BACKEND_URL__ 占位符
# 默认 http://backend:7860（Docker Compose 服务名 + 端口）
NGINX_BACKEND_URL="${NGINX_BACKEND_URL:-http://backend:7860}"
sed "s|__NGINX_BACKEND_URL__|$NGINX_BACKEND_URL|g" /etc/nginx/nginx.conf > /tmp/nginx.conf
mv /tmp/nginx.conf /etc/nginx/nginx.conf

exec nginx -g "daemon off;"
