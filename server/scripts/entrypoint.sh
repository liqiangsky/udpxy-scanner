#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/app/data}"

# 启动前先迁移旧数据（零维护，自动对齐新旧字段）
python /app/server/scripts/auto_migrate.py "$DATA_DIR"

# 启动服务
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-7860}"
