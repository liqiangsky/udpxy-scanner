"""
零维护历史数据迁移——启动时自动执行。

覆盖所有 SQLite 数据库文件，逐表自动对齐新旧字段。
schema 任意增删字段——改 database.py 就行，这个文件永远不用动。

流程：
  读取 data.db → 删旧库 → 按最新 schema 重建 → 写回共同字段

兼容旧 3 文件时代（udpxy_scanner.db / iptv_list.db / source_cache.db），
自动合并为 data.db 后走统一迁移流程。
"""
import os
import sys
import sqlite3

DATA_DIR = sys.argv[1] if len(sys.argv) > 1 else "/app/data"
SERVER_DIR = os.path.join(os.path.dirname(__file__), "..")

_TARGET_DB = "data.db"
# 表名映射（旧表名 → 新表名）
_TABLE_RENAME = {
    "iptv_list": "host",
    "api_subscriptions": "subscription",
    "settings": "parameter",
    "scan_config": "config",
    "source_cache": "cache",
}


def _to_dict(row) -> dict:
    return dict(zip(row.keys(), row))


_OLD_FILES = {
    "udpxy_scanner.db": ("settings", "scan_config", "api_subscriptions"),
    "iptv_list.db": ("iptv_list",),
    "source_cache.db": ("source_cache",),
}


def _merge_three_old_dbs(data_dir: str, target_path: str):
    """检测旧 3 文件，合并为统一的 data.db（保留原始列类型）"""
    found = {}
    for fname in _OLD_FILES:
        fpath = os.path.join(data_dir, fname)
        if os.path.exists(fpath) and not fpath.endswith(("-wal", "-shm")):
            found[fname] = fpath

    if not found:
        return  # 没有旧文件，无需处理

    print(f"📦 检测到旧版 3 文件数据库，合并为 {_TARGET_DB}...")
    old_data = {}
    for fname, fpath in found.items():
        old = sqlite3.connect(fpath)
        old.row_factory = sqlite3.Row
        for table in _OLD_FILES[fname]:
            if not old.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone():
                continue
            cols_info = old.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = [r["name"] for r in cols_info]
            col_types = [r["type"] for r in cols_info]
            rows = old.execute(f"SELECT * FROM {table}").fetchall()
            old_data[table] = {
                "cols": col_names,
                "types": col_types,
                "rows": [_to_dict(r) for r in rows],
            }
        old.close()

    if old_data:
        conn = sqlite3.connect(target_path)
        for table, data in old_data.items():
            col_defs = ", ".join(
                f"{n} {t}" for n, t in zip(data["cols"], data["types"])
            )
            col_names = ", ".join(data["cols"])
            placeholders = ",".join("?" for _ in data["cols"])
            conn.execute(f"CREATE TABLE {table} ({col_defs})")
            values = [tuple(row[c] for c in data["cols"]) for row in data["rows"]]
            if values:
                conn.executemany(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    values,
                )
        conn.commit()
        conn.close()
        total = sum(len(d["rows"]) for d in old_data.values())
        print(f"  ✓ 合并完成，共 {total} 条记录")

    # 清理旧文件和 WAL/shm
    for fname in _OLD_FILES:
        for suf in ("", "-wal", "-shm"):
            f = os.path.join(data_dir, fname) + suf
            if os.path.exists(f):
                os.remove(f)
    print(f"  🗑️  旧 3 文件已清理")
    return old_data


def _read_old_data(db_path: str) -> dict:
    old = sqlite3.connect(db_path)
    old.row_factory = sqlite3.Row
    tables = old.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    data = {}
    for (table,) in tables:
        cols = [r["name"] for r in old.execute(f"PRAGMA table_info({table})")]
        rows = old.execute(f"SELECT * FROM {table}").fetchall()
        data[table] = {"cols": cols, "rows": [_to_dict(r) for r in rows]}
    old.close()
    return data


def _delete_db(db_path: str):
    for suffix in ("", "-wal", "-shm"):
        f = db_path + suffix
        if os.path.exists(f):
            os.remove(f)


# 列名映射：旧列名 -> 新列名
_COLUMN_RENAME = {
    "host": {"createTime": "createdAt", "updateTime": "updatedAt"},
    "cache": {"updateTime": "updatedAt"},
}

_DATE_COLS = {
    "config": ("createdAt", "updatedAt"),
    "subscription": ("createdAt", "updatedAt", "lastFetchAt"),
    "cache": ("createdAt", "updatedAt"),
    "host": ("createdAt", "updatedAt"),
}


def _convert_date_str(conn, table: str, col: str):
    """将 TEXT 类型日期字符串转为秒级时间戳"""
    import time as _time
    import re as _re

    # 匹配 ISO 格式或 SQLite datetime('now') 格式
    _PATTERNS = [
        _re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"),       # ISO with T
        _re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"),       # space separator
    ]

    rows = conn.execute(f"SELECT rowid, {col} FROM {table} WHERE {col} IS NOT NULL AND {col} != ''").fetchall()
    updates = []
    for rowid, val in rows:
        if isinstance(val, (int, float)):
            if val > 1e12:  # 毫秒转秒
                updates.append((int(val / 1000), rowid))
            continue
        val_str = str(val)
        ts = None
        for pat in _PATTERNS:
            if pat.match(val_str):
                try:
                    # Python 3.7+ 支持从多种格式解析
                    from datetime import datetime as _dt
                    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                        try:
                            ts = int(_dt.strptime(val_str[:19], fmt).timestamp())
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
                break
        if ts is not None:
            updates.append((ts, rowid))

    if updates:
        conn.executemany(f"UPDATE {table} SET {col}=? WHERE rowid=?", updates)


def _write_common(db_path: str, old_data: dict):
    """只写回新旧表共同的字段。"""
    new = sqlite3.connect(db_path)
    new.row_factory = sqlite3.Row

    for table, data in old_data.items():
        target = _TABLE_RENAME.get(table, table)
        t = new.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (target,)
        ).fetchone()
        if not t:
            print(f"  ⚠  新 schema 无 {table} -> {target} 表，跳过")
            continue

        new_cols = {r["name"] for r in new.execute(f"PRAGMA table_info({target})")}
        # 应用列名映射（旧列名 -> 新列名）
        rename_map = _COLUMN_RENAME.get(target, {})
        def _map_col(c):
            return rename_map.get(c, c)
        mapped_cols = [_map_col(c) for c in data["cols"]]
        common = [c for c in mapped_cols if c in new_cols]
        if not common:
            continue

        placeholders = ",".join("?" for _ in common)
        col_names = ", ".join(common)
        # 按新列名取值（旧列名通过映射找到对应的旧数据 key）
        col_to_old = {rename_map.get(c, c): c for c in data["cols"]}
        values = []
        for row in data["rows"]:
            vals = tuple(row[col_to_old[c]] for c in common)
            values.append(vals)
        if not values:
            print(f"  - {table}: 空表")
            continue

        cmd = "INSERT OR REPLACE" if table in ("settings", "parameters") else "INSERT OR IGNORE"
        new.executemany(
            f"{cmd} INTO {target} ({col_names}) VALUES ({placeholders})",
            values,
        )
        new.commit()
        label = f"{table} -> {target}" if table != target else table
        print(f"  ✓ {label}: {len(values)} 条，字段: {common}")

    new.close()


def migrate():
    sys.path.insert(0, SERVER_DIR)

    target_path = os.path.join(DATA_DIR, _TARGET_DB)

    # 兼容旧 3 文件：先合并为 data.db
    _merge_three_old_dbs(DATA_DIR, target_path)

    if not os.path.exists(target_path):
        return  # 全新部署，无需迁移

    print(f"📦 检测到 {_TARGET_DB}，开始迁移...")
    old_data = _read_old_data(target_path)
    _delete_db(target_path)
    print(f"  🗑️  旧文件已删除")

    os.environ["DB_PATH"] = target_path
    import importlib
    import db.database as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    _write_common(target_path, old_data)
    # 将旧数据中的日期字符串转为时间戳
    conv = sqlite3.connect(target_path)
    conv.row_factory = sqlite3.Row
    for table, cols in _DATE_COLS.items():
        t = conv.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if t:
            for col in cols:
                _convert_date_str(conv, table, col)
    conv.commit()

    # 回填 cache.active：host 表中有同名 host 的标记为 1
    cur = conv.execute("UPDATE cache SET active=1 WHERE host IN (SELECT host FROM host)")
    activated = cur.rowcount
    conv.commit()
    conv.close()
    print(f"✅ {_TARGET_DB} 迁移完成（无备份残留）\n")


if __name__ == "__main__":
    migrate()
