#!/usr/bin/env bash
# import.sh - 手动恢复 backup.sql 到已运行的数据库
# 适用场景: 目标机器的 postgres 数据卷已初始化过（自动导入被跳过），需要手动恢复
# 用法: ./import.sh [-y]      （-y 跳过确认提示）
# 测试/特殊环境: UDXPY_DB_CONTAINER=容器名 ./import.sh 可指定其他容器
set -euo pipefail

CONTAINER="${UDXPY_DB_CONTAINER:-udpxy-scanner-db}"
DB_USER="udpxy"
DB_NAME="udpxy"
TABLES="cache config host parameter subscription"       # 空格分隔，用于循环展示
TABLES_CSV="cache, config, host, parameter, subscription"  # SQL 用逗号分隔
ASSUME_YES=0
[ "${1:-}" = "-y" ] && ASSUME_YES=1

cd "$(dirname "$0")"
BACKUP="backup.sql"

RED='\033[31m'; GREEN='\033[32m'; YELLOW='\033[33m'; CYAN='\033[36m'; NC='\033[0m'

# 1. 前置检查
if ! docker ps --filter "name=$CONTAINER" --filter "status=running" --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo -e "${RED}[X] 容器 $CONTAINER 未在运行。请先: docker compose up -d db${NC}"
  exit 1
fi
[ -f "$BACKUP" ] || { echo -e "${RED}[X] 未找到 $BACKUP（请把备份文件放到项目根目录）${NC}"; exit 1; }

CRLF=$(tr -dc '\r' < "$BACKUP" | wc -c)
[ "$CRLF" -ne 0 ] && { echo -e "${RED}[X] backup.sql 含 $CRLF 处 CRLF 行尾，文件已损坏，请重新导出${NC}"; exit 1; }

# 2. 从 backup.sql 抽数据段（COPY 块 + setval），不含 schema（表已由应用建好）
awk '
  /^COPY public\./            { keep=1; print; next }
  keep && /^\\\./             { print; keep=0; next }
  keep                        { print }
  /^SELECT pg_catalog\.setval/ { print }
' "$BACKUP" > /tmp/import_data.sql

COPY_COUNT=$(grep -c '^COPY public\.' /tmp/import_data.sql)
[ "$COPY_COUNT" -eq 0 ] && { echo -e "${RED}[X] backup.sql 中没有数据段(COPY)，文件无效${NC}"; rm -f /tmp/import_data.sql; exit 1; }

echo -e "${GREEN}[1/3] backup.sql 校验通过（CRLF=0，数据段=$COPY_COUNT）${NC}"

# 3. 数据对比
echo -e "${YELLOW}[2/3] 即将覆盖导入，数据对比（备份 -> 当前）:${NC}"
awk '
  /^COPY public\./ { table=$2; sub("public\\.", "", table); n=0; next }
  /^\\\./          { if (table != "") { print table, n; table="" } next }
  table != ""      { n++ }
' "$BACKUP" | while read -r t n; do
  cur=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT count(*) FROM $t" 2>/dev/null || echo "?")
  printf "      %-14s %8s -> %-8s\n" "$t" "$n" "$cur"
done

echo -e "${YELLOW}>> 建议先暂停应用再恢复: docker compose stop backend（恢复后 start）${NC}"
if [ "$ASSUME_YES" -ne 1 ]; then
  read -r -p ">> 将清空以上 5 张表并导入备份数据（事务保护，失败自动回滚）。确认? [y/N] " ans
  [ "$ans" = "y" ] || { echo "已取消"; rm -f /tmp/import_data.sql; exit 0; }
fi

# 4. 导入（docker cp 进容器执行，避免宿主机管道编码问题；单事务：TRUNCATE+导入要么全成要么全回滚）
docker cp /tmp/import_data.sql "$CONTAINER:/tmp/import_data.sql"
docker exec "$CONTAINER" sh -c \
  "psql -U $DB_USER -d $DB_NAME -v ON_ERROR_STOP=1 --single-transaction \
   -c \"TRUNCATE $TABLES_CSV RESTART IDENTITY;\" -f /tmp/import_data.sql" > /dev/null
docker exec "$CONTAINER" rm -f /tmp/import_data.sql
rm -f /tmp/import_data.sql

echo -e "${GREEN}[3/3] 恢复完成，各表行数:${NC}"
for t in $TABLES; do
  n=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT count(*) FROM $t")
  printf "      %-14s %s 行\n" "$t" "$n"
done
echo -e "${CYAN}>> 完成。如暂停了 backend，执行 docker compose start backend${NC}"
