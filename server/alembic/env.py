"""
Alembic 环境配置 - PostgreSQL 生产级设置
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text
from alembic import context

# 添加 server 目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.models import Base  # noqa: E402

# 导入 Base 用于 autogenerate
target_metadata = Base.metadata

# 从环境变量获取数据库连接 URL
DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/udpxy_scanner")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = DB_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    config = context.config
    config.set_main_option("sqlalchemy.url", DB_URL)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # 【关键配置 1】设置锁超时：如果 3 秒内拿不到锁，自动断开退出，绝不卡死生产 DB
        connection.execute(text("SET lock_timeout = '3s';"))
        connection.execute(text("SET statement_timeout = '30s';"))

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # 【关键配置 2】启用事务隔离，确保迁移失败时能整体 Rollback
            transaction_per_migration=True,
            # 允许检测字段类型变更
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

        # 【关键配置 3】显式提交：SET 语句先触发了 autobegin，alembic 内部
        # 事务嵌套会失效且从不 commit，连接归还时整体 ROLLBACK（迁移白跑）。
        # 若内部已提交，这里是幂等空操作。
        connection.commit()


# 注意：alembic 以模块方式加载 env.py（模块名不是 __main__），
# 不能包在 if __name__ == "__main__" 里，否则迁移静默不执行
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
