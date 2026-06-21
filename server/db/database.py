import sqlite3
import os
import time
import threading
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "udpxy_scanner.db")
CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", "source_cache.db")
IPTV_DB_PATH = os.getenv("IPTV_DB_PATH", "iptv_list.db")

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
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    with _local_lock:
        setattr(_local, key, conn)
    return conn


def init_cache_db():
    """初始化源缓存数据库（source_cache 表）"""
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS source_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sourceType TEXT NOT NULL,
            host TEXT NOT NULL,
            geoRegion TEXT DEFAULT '',
            geoOperator TEXT DEFAULT '',
            createdAt TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_cache_unique ON source_cache(sourceType, host);
        CREATE INDEX IF NOT EXISTS idx_source_cache_host ON source_cache(host);
    """)
    conn.commit()
    conn.close()


def init_iptv_db():
    """初始化活源池数据库（iptv_list 表）"""
    conn = sqlite3.connect(IPTV_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS iptv_list (
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
            createTime INTEGER NOT NULL,
            updateTime INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_iptv_unique ON iptv_list(host, target, channelName);
        CREATE INDEX IF NOT EXISTS idx_region_operator ON iptv_list(region, operator);
        CREATE INDEX IF NOT EXISTS idx_geo ON iptv_list(geoRegion, geoOperator);
        CREATE INDEX IF NOT EXISTS idx_iptv_host ON iptv_list(host);
        CREATE INDEX IF NOT EXISTS idx_iptv_sourceType ON iptv_list(sourceType);
    """)
    conn.commit()
    conn.close()


def init_db():
    """初始化主数据库（settings + scan_config + templates + sessions）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 高并发优化
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS scan_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dataSource TEXT NOT NULL,
            templateRegion TEXT DEFAULT '',
            templateOperator TEXT DEFAULT '',
            templateTargetName TEXT DEFAULT '',
            templateTargetAddress TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            createdAt TEXT DEFAULT (datetime('now')),
            updatedAt TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS api_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            uid TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            fetchCron TEXT DEFAULT '',
            lastFetchAt TEXT DEFAULT NULL,
            createdAt TEXT DEFAULT (datetime('now')),
            updatedAt TEXT DEFAULT (datetime('now'))
        );
    """)

    # 初始化默认密码
    row = conn.execute(
        "SELECT value FROM settings WHERE key='password_hash'"
    ).fetchone()

    if not row:
        import hashlib

        default_hash = hashlib.sha256(
            os.getenv("UDPXY_SCANNER_PASSWORD", "admin").encode()
        ).hexdigest()

        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('password_hash', ?)",
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
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (k, v)
        )

    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """主数据库连接管理（线程级持久连接）"""
    conn = _get_persistent_conn(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@contextmanager
def get_cache_db():
    """缓存数据库连接管理（source_cache 表，线程级持久连接）"""
    conn = _get_persistent_conn(CACHE_DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@contextmanager
def get_iptv_db():
    """活源池数据库连接管理（iptv_list 表，线程级持久连接）"""
    conn = _get_persistent_conn(IPTV_DB_PATH)
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
                "SELECT value FROM settings WHERE key=?",
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
