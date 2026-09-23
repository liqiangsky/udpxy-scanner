"""
数据库连接配置 - PostgreSQL
"""
import os
import time
import threading
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from db.models import Base, Parameter

logger = logging.getLogger(__name__)

# 数据库写锁：序列化进程内所有写事务。
# PG 时代不再是防“库锁死”的手段（那是 SQLite 文件锁的问题），现在的作用：
# 1) 多语句读-改-写流程（删 host 联动清 cache、订阅 uid 组迁移等）避免自相竞争
# 2) 避免并发多行事务在 host/cache 上交叉加行锁导致 PG 死锁（40P01）
# 正确性兜底靠唯一约束 + ON CONFLICT upsert；锁内无网络 I/O，持有均为毫秒级
db_write_lock = threading.Lock()

# 设置缓存
_settings_cache = {}
_settings_cache_ttl = 30
_settings_cache_lock = threading.Lock()

# SQLAlchemy engine（单例，进程级）
_engine = None
_SessionFactory = None


def _get_engine():
    """获取或创建 SQLAlchemy engine（线程安全）"""
    global _engine, _SessionFactory
    if _engine is None:
        with threading.Lock():
            if _engine is None:
                db_url = os.getenv("DATABASE_URL")
                if not db_url:
                    raise ValueError("DATABASE_URL 环境变量未设置")
                
                logger.info(f"📊 连接 PostgreSQL: {db_url.split('@')[-1]}")
                
                _engine = create_engine(
                    db_url,
                    poolclass=QueuePool,
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    echo=False,
                )
                
                _SessionFactory = sessionmaker(
                    bind=_engine,
                    autocommit=False,
                    autoflush=False,
                    expire_on_commit=False,
                )
                logger.info("✅ PostgreSQL 引擎初始化完成")
    return _engine, _SessionFactory


def _ensure_host_unique_constraint(engine):
    """补齐 host(host, target, channel_name) 唯一约束。

    create_all 不会给已存在的表添加新约束，老库（如 SQLite 迁移过来的 PG 库）
    缺此约束会导致扫描入库 ON CONFLICT 报错，这里幂等补齐。
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        exists = conn.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = 'uq_host_host_target_channel' "
                "AND conrelid = 'host'::regclass"
            )
        ).fetchone()
        if exists:
            return
        conn.execute(
            text(
                "ALTER TABLE host ADD CONSTRAINT uq_host_host_target_channel "
                "UNIQUE (host, target, channel_name)"
            )
        )
        conn.commit()
        logger.info("✅ 已补齐 host 表唯一约束 uq_host_host_target_channel")


def _ensure_cache_unique_constraint(engine):
    """补齐 cache(host) 唯一约束。

    cache_sources 改为 ON CONFLICT upsert 后依赖此约束；
    老库若缺此约束，先去重（保留 updated_at 最新的一条）再补齐。
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        exists = conn.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = 'uq_cache_host' "
                "AND conrelid = 'cache'::regclass"
            )
        ).fetchone()
        if exists:
            return
        # 先去重：同 host 多条时按 updated_at/created_at 保留最新一条
        deleted = conn.execute(
            text(
                "DELETE FROM cache a USING cache b "
                "WHERE a.host = b.host "
                "AND a.id < b.id"
            )
        )
        if deleted.rowcount:
            logger.info(f"✅ cache 表去重完成，删除 {deleted.rowcount} 条重复行")
        conn.execute(
            text(
                "ALTER TABLE cache ADD CONSTRAINT uq_cache_host UNIQUE (host)"
            )
        )
        conn.commit()
        logger.info("✅ 已补齐 cache 表唯一约束 uq_cache_host")


def _ensure_id_sequences(engine):
    """重置所有表的自增序列到 MAX(id)。

    SQLite -> PG 迁移时数据带显式 id 插入，但序列不会自动跟进，
    导致后续 INSERT 撞主键（duplicate key value violates unique
    constraint "xxx_pkey"）。这里按表幂等校正（每次 setval 到当前 MAX(id)）。
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        # information_schema 里带 serial/bigserial 默认值的表
        rows = conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND column_default LIKE 'nextval(%'"
            )
        ).fetchall()
        for table_name, column_name in rows:
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', '{column_name}'), "
                    f"COALESCE((SELECT MAX({column_name}) FROM {table_name}), 0))"
                )
            )
            logger.info(f"✅ 序列已同步: {table_name}.{column_name} -> MAX(id)")
        conn.commit()


def init_db():
    """初始化数据库（创建所有表）"""
    engine, _ = _get_engine()
    Base.metadata.create_all(engine)
    logger.info("✅ 数据库表创建完成")

    # create_all 不会给已存在的表补约束，老库需要幂等修复
    _ensure_host_unique_constraint(engine)
    _ensure_cache_unique_constraint(engine)

    # 迁移过来的库序列可能落后于 MAX(id)，幂等校正
    _ensure_id_sequences(engine)

    # 初始化默认配置（必须与 GlobalSettingsUpdate 的默认值/单位一致：
    # timeout 单位是秒，老默认值 2000 会让全新部署的验证请求超时 33 分钟）
    default_settings = {
        "scan_cron": "",
        "concurrency": "30",
        "timeout": "5",
        "config_delay": "3",
        "janitor_cron": "",
        "push_api_key": ""
    }
    with _SessionFactory() as session:
        for k, v in default_settings.items():
            existing = session.query(Parameter).filter(Parameter.key == k).first()
            if not existing:
                session.add(Parameter(key=k, value=v))
        session.commit()
    
    logger.info("✅ 数据库初始化完成")


@contextmanager
def get_db():
    """数据库会话管理（yield Session 对象）"""
    engine, SessionFactory = _get_engine()
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_setting(key: str, default: str) -> str:
    """获取设置值（带缓存）"""
    now = time.time()
    with _settings_cache_lock:
        cached = _settings_cache.get(key)
        if cached and now - cached[1] < _settings_cache_ttl:
            return cached[0]
    try:
        with get_db() as session:
            row = session.query(Parameter).filter(Parameter.key == key).first()
            val = row.value if row else default
            with _settings_cache_lock:
                _settings_cache[key] = (val, now)
            return val
    except Exception:
        return default


import asyncio as _asyncio


async def run_in_thread(func, *args, **kwargs):
    """将同步函数放到线程池执行，避免阻塞事件循环"""
    return await _asyncio.to_thread(func, *args, **kwargs)
