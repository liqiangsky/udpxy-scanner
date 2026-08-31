#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/app/data}"

# 运行 Alembic 迁移（如果数据库已存在且需要迁移）
if [ -f "$DATA_DIR/data.db" ]; then
    cd /app/server
    # 检查是否有 alembic_version 表
    if python3 -c "import sqlite3; c=sqlite3.connect('$DATA_DIR/data.db'); c.execute('SELECT 1 FROM alembic_version'); c.close()" 2>/dev/null; then
        # 已有 alembic_version，直接升级
        echo "[Alembic] 检测到 alembic_version，执行 upgrade head..."
        alembic upgrade head || echo "[Alembic] upgrade head 失败，但应用继续启动"
    else
        # 旧数据库：标记为 0001_initial（跳过建表迁移），然后升级到 head
        echo "[Alembic] 旧数据库，标记 0001_initial..."
        alembic stamp 0001_initial || echo "[Alembic] stamp 失败，跳过"
        echo "[Alembic] 执行 upgrade head..."
        alembic upgrade head || echo "[Alembic] upgrade head 失败，但应用继续启动"
    fi
fi

# 启动服务
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-7860}" --timeout-graceful-shutdown 5
