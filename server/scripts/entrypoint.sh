#!/bin/sh
set -e

# 启动服务
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-7860}" --timeout-graceful-shutdown 5
