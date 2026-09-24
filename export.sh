#!/usr/bin/env bash
# export.sh - 一键导出 udpxy-scanner 数据库数据到 backup.sql（macOS / Linux / Git Bash）
# 用法: 在项目根目录执行  ./export.sh   或   bash export.sh
# 流程: 容器内 pg_dump -> docker cp 拷出 -> 自动校验（CRLF / 数据段 / 各表行数）
set -euo pipefail

CONTAINER="udpxy-scanner-db"
DB_USER="udpxy"
DB_NAME="udpxy"

cd "$(dirname "$0")"
OUT_FILE="backup.sql"

RED='\033[31m'; GREEN='\033[32m'; CYAN='\033[36m'; NC='\033[0m'

# 1. 容器运行检查
if ! docker ps --filter "name=$CONTAINER" --filter "status=running" --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo -e "${RED}[X] 容器 $CONTAINER 未在运行。请先执行: docker compose up -d db${NC}"
  exit 1
fi

echo "[1/3] 正在导出 $CONTAINER -> backup.sql ..."

# 2. 容器内导出 + docker cp 原样拷出（不经宿主机管道，避免编码/行尾差异）
docker exec "$CONTAINER" sh -c "pg_dump -U $DB_USER --no-owner --no-privileges -d $DB_NAME > /tmp/backup.sql"
docker cp "$CONTAINER:/tmp/backup.sql" "$OUT_FILE"
docker exec "$CONTAINER" rm -f /tmp/backup.sql >/dev/null

# 3. 校验
SIZE=$(wc -c < "$OUT_FILE" | tr -d ' ')
CRLF=$(tr -dc '\r' < "$OUT_FILE" | wc -c)
COPY_COUNT=$(grep -c '^COPY public\.' "$OUT_FILE" || true)

echo -e "${GREEN}[2/3] 导出完成: $OUT_FILE ($((SIZE / 1024)) KB)${NC}"

if [ "$CRLF" -ne 0 ]; then
  echo -e "${RED}[X] 校验失败: 检测到 $CRLF 处 CRLF 行尾，数据会被污染，请勿使用该文件${NC}"
  exit 1
fi
if [ "$COPY_COUNT" -eq 0 ]; then
  echo -e "${RED}[X] 校验失败: 未发现数据段(COPY)，请检查数据库里是否有数据${NC}"
  exit 1
fi

echo -e "${GREEN}[3/3] 校验通过: CRLF=0, 数据段=$COPY_COUNT，各表行数:${NC}"
awk '
  /^COPY public\./ { table=$2; sub("public\\.", "", table); n=0; next }
  /^\\\./          { if (table != "") { printf "      %-14s %d 行\n", table, n; table="" } next }
  table != ""      { n++ }
' "$OUT_FILE"

echo ""
echo -e "${CYAN}>> 把 backup.sql 拷到目标电脑的项目根目录，首次 docker compose up -d 会自动导入。${NC}"
