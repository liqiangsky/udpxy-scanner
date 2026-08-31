import os
import time
import threading
import logging
import shutil
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from db.models import Base, Parameter

logger = logging.getLogger(__name__)

# 全局 SQLite 写锁：序列化所有并发写入，防止 database is locked
db_write_lock = threading.Lock()

DB_PATH = os.getenv("DB_PATH", "data.db")

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
                os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
                # SQLite: use check_same_thread=False + StaticPool for simplicity
                # For production with uvicorn workers, consider QueuePool
                _engine = create_engine(
                    f"sqlite:///{DB_PATH}",
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool,
                )
                # 应用 SQLite 优化 PRAGMAs
                @event.listens_for(_engine, "connect")
                def set_sqlite_pragma(conn, record):
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.execute("PRAGMA temp_store=MEMORY")
                    cursor.execute("PRAGMA cache_size=-64000")
                    cursor.close()

                _SessionFactory = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _engine, _SessionFactory


def _ensure_columns(engine):
    """检查并补全所有表的缺失列（兼容旧数据库）"""
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue
        existing_cols = {col['name'] for col in inspector.get_columns(table_name)}
        for col in table.columns:
            # col.name 是数据库实际列名（如 dataSource），col.key 是 Python 属性名（如 data_source）
            db_col_name = col.name
            if db_col_name not in existing_cols:
                col_type = col.type.compile(engine.dialect)
                nullable = "NULL" if col.nullable else "NOT NULL DEFAULT ''"
                sql = f"ALTER TABLE {table_name} ADD COLUMN {db_col_name} {col_type} {nullable}"
                try:
                    with engine.connect() as conn:
                        conn.execute(text(sql))
                        conn.commit()
                    logger.info(f"✅ 补全列: {table_name}.{db_col_name}")
                except Exception as e:
                    logger.warning(f"⚠️ 补全列失败 {table_name}.{db_col_name}: {e}")


def init_db():
    """初始化数据库（创建所有表和默认数据）"""
    # 启动后台维护线程
    start_maintenance_thread()

    # 启动时检查数据库完整性
    if os.path.exists(DB_PATH) and not check_integrity():
        logger.warning("启动时数据库完整性检查失败，尝试备份后重建...")
        _backup_and_recover()
        return

    # 创建所有表
    engine, _ = _get_engine()
    Base.metadata.create_all(engine)

    # 检查并补全旧数据库缺失的列
    _ensure_columns(engine)

    # 初始化默认密码
    with _SessionFactory() as session:
        row = session.query(Parameter).filter(Parameter.key == "password_hash").first()
        if not row:
            import hashlib
            default_hash = "pbkdf2$" + hashlib.pbkdf2_hmac(
                "sha256",
                os.getenv("PASSWORD", "admin").encode(),
                b"udpxy-scanner-password-salt",
                100000
            ).hex()
            param = Parameter(key="password_hash", value=default_hash)
            session.add(param)
        session.commit()

    # 初始化默认配置
    default_settings = {
        "scan_cron": "",
        "concurrency": "64",
        "timeout": "2000",
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


def check_integrity() -> bool:
    """检查数据库完整性，返回 True 表示正常"""
    try:
        engine, _ = _get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA integrity_check")).fetchone()
            if result[0] == "ok":
                logger.debug("数据库完整性检查通过")
                return True
            else:
                logger.error(f"数据库完整性检查失败: {result[0]}")
                return False
    except Exception as e:
        logger.error(f"数据库完整性检查异常: {e}")
        return False


def periodic_maintenance():
    """定期维护任务（仅做完整性检查，不做 VACUUM）"""
    while True:
        time.sleep(3600)  # 每小时
        try:
            check_integrity()
        except Exception as e:
            logger.error(f"定期维护失败: {e}")


def start_maintenance_thread():
    """启动后台维护线程（守护线程，随主进程退出）"""
    t = threading.Thread(target=periodic_maintenance, daemon=True)
    t.start()
    logger.info("数据库维护线程已启动")


def _backup_and_recover():
    """备份损坏的数据库并尝试恢复"""
    try:
        db_dir = os.path.dirname(DB_PATH) or "."
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(db_dir, f"udpxy_backup_{timestamp}.db")

        # 创建备份（即使损坏也保留现场）
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_path)
            logger.info(f"已创建数据库备份: {backup_path}")

        # 删除损坏的文件，重新初始化
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            # 同时删除 WAL 文件（如果有）
            wal_path = DB_PATH + "-wal"
            shm_path = DB_PATH + "-shm"
            for p in [wal_path, shm_path]:
                if os.path.exists(p):
                    os.remove(p)

        # 重建表结构（数据丢失，需用户重新导入）
        init_db()
        logger.warning("数据库已重建，原有数据已丢失。请检查备份文件恢复。")
    except Exception as e:
        logger.error(f"数据库恢复失败: {e}", exc_info=True)


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


def _row_to_dict(row):
    """将 SQLAlchemy ORM 行转换为 dict，排除内部状态"""
    if row is None:
        return None
    return {key: getattr(row, key) for key in row.__mapper__.column_attrs.keys()}


async def run_in_thread(func, *args, **kwargs):
    """将同步函数放到线程池执行，避免阻塞事件循环"""
    return await _asyncio.to_thread(func, *args, **kwargs)
