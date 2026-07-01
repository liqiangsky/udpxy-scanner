import sqlite3
import os
import time
import threading
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "data.db")

_settings_cache = {}
_settings_cache_ttl = 30
_settings_cache_lock = threading.Lock()

_local = threading.local()
_local_lock = threading.Lock()


def _get_persistent_conn(db_path: str) -> sqlite3.Connection:
    key = db_path
    conn = getattr(_local, key, None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")
    with _local_lock:
        setattr(_local, key, conn)
    return conn


def init_db():
    """初始化数据库（全部表都在 data.db 中）"""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 高并发优化
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS parameter (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dataSource TEXT NOT NULL,
            templateRegion TEXT DEFAULT '',
            templateOperator TEXT DEFAULT '',
            templateTargetName TEXT DEFAULT '',
            templateTargetAddress TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            createdAt INTEGER DEFAULT 0,
            updatedAt INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_config_enabled ON config(enabled);

        CREATE TABLE IF NOT EXISTS subscription (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            uid TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            fetchCron TEXT DEFAULT '',
            lastFetchAt INTEGER DEFAULT NULL,
            createdAt INTEGER DEFAULT 0,
            updatedAt INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_subscription_enabled_cron ON subscription(enabled, fetchCron);

        CREATE TABLE IF NOT EXISTS cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sourceType TEXT NOT NULL,
            host TEXT NOT NULL,
            geoRegion TEXT DEFAULT '',
            geoOperator TEXT DEFAULT '',
            active INTEGER DEFAULT 0,
            status INTEGER DEFAULT 0,
            createdAt INTEGER DEFAULT 0,
            updatedAt INTEGER DEFAULT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cache_unique ON cache(host);
        CREATE INDEX IF NOT EXISTS idx_cache_sourceType ON cache(sourceType);

        CREATE TABLE IF NOT EXISTS host (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL,
            ip TEXT NOT NULL,
            port INTEGER NOT NULL,
            sourceType TEXT DEFAULT '',
            sourceName TEXT DEFAULT '',
            region TEXT NOT NULL,
            operator TEXT NOT NULL,
            geoRegion TEXT DEFAULT '',
            geoOperator TEXT DEFAULT '',
            delay INTEGER NOT NULL,
            protocol TEXT NOT NULL,
            target TEXT NOT NULL,
            channelName TEXT NOT NULL,
            createdAt INTEGER NOT NULL,
            updatedAt INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_host_unique ON host(host, target, channelName);
        CREATE INDEX IF NOT EXISTS idx_host_region_operator ON host(region, operator);
        CREATE INDEX IF NOT EXISTS idx_host_geo ON host(geoRegion, geoOperator);
        CREATE INDEX IF NOT EXISTS idx_host_host ON host(host);
        CREATE INDEX IF NOT EXISTS idx_host_sourceType ON host(sourceType);
        CREATE INDEX IF NOT EXISTS idx_host_geoRegion ON host(geoRegion);
        CREATE INDEX IF NOT EXISTS idx_host_geoOperator ON host(geoOperator);
    """)

    # 初始化默认密码
    row = conn.execute(
        "SELECT value FROM parameter WHERE key='password_hash'"
    ).fetchone()

    if not row:
        import hashlib

        default_hash = "pbkdf2$" + hashlib.pbkdf2_hmac(
            "sha256",
            os.getenv("UDPXY_SCANNER_PASSWORD", "admin").encode(),
            b"udpxy-scanner-password-salt",
            100000
        ).hex()

        conn.execute(
            "INSERT INTO parameter (key, value) VALUES ('password_hash', ?)",
            (default_hash,)
        )

    # 初始化默认配置
    default_settings = {
        "scan_cron": "",
        "concurrency": "64",
        "timeout": "2000",
        "config_delay": "3",
        "janitor_cron": "",
        "push_api_key": ""
    }

    for k, v in default_settings.items():
        conn.execute(
            "INSERT OR IGNORE INTO parameter (key, value) VALUES (?, ?)",
            (k, v)
        )

    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """数据库连接管理（全部表共用 data.db，线程级持久连接）"""
    conn = _get_persistent_conn(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_setting(key: str, default: str) -> str:
    now = time.time()
    with _settings_cache_lock:
        cached = _settings_cache.get(key)
        if cached and now - cached[1] < _settings_cache_ttl:
            return cached[0]
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT value FROM parameter WHERE key=?",
                (key,)
            ).fetchone()
            val = row["value"] if row else default
            with _settings_cache_lock:
                _settings_cache[key] = (val, now)
            return val
    except Exception:
        return default


import asyncio as _asyncio


async def run_in_thread(func, *args, **kwargs):
    """将同步函数放到线程池执行，避免阻塞事件循环"""
    return await _asyncio.to_thread(func, *args, **kwargs)
