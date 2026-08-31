"""
Alembic 环境配置
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 添加 server 目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.models import Base  # noqa: E402

# 导入 Base 用于 autogenerate
target_metadata = Base.metadata

# 从环境变量获取数据库路径
DB_PATH = os.getenv("DB_PATH", "data.db")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = f"sqlite:///{DB_PATH}"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    config = context.config
    # SQLite needs check_same_thread=False for multi-threaded access
    connect_args = {"check_same_thread": False} if "sqlite" in DB_PATH else {}
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if __name__ == "__main__":
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
