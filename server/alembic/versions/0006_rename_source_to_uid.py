"""统一来源标识为 uid：cache.source_type -> uid，host.source_type -> uid 并删除 source_name

多个订阅可共用同一 uid（如多个 GitHub 镜像地址都填 github），
来源字段语义就是 subscription.uid，sourceName 不再有存在意义。

Revision ID: 20260922_06
Revises: 20260922_05
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260922_06"
down_revision = "20260922_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- cache: source_type -> uid ---
    inspector = sa.inspect(op.get_bind())
    cache_cols = [c["name"] for c in inspector.get_columns("cache")]
    if "source_type" in cache_cols and "uid" not in cache_cols:
        op.alter_column("cache", "source_type", new_column_name="uid",
                        existing_type=sa.String(), existing_nullable=False)

    # --- host: source_type -> uid，source_name 数据并入 uid 后删列 ---
    host_cols = [c["name"] for c in inspector.get_columns("host")]
    if "source_type" in host_cols and "uid" not in host_cols:
        op.alter_column("host", "source_type", new_column_name="uid",
                        existing_type=sa.String(), existing_nullable=True)
    if "source_name" in host_cols and "uid" in host_cols:
        # 历史数据兜底：uid 为空但 source_name 有值的行，用 source_name 补 uid
        op.execute(sa.text(
            "UPDATE host SET uid = source_name WHERE (uid IS NULL OR uid = '') AND source_name IS NOT NULL AND source_name != ''"
        ))
        op.drop_column("host", "source_name")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    host_cols = [c["name"] for c in inspector.get_columns("host")]
    if "source_name" not in host_cols:
        op.add_column("host", sa.Column("source_name", sa.String(), nullable=False, server_default=""))
    if "uid" in host_cols and "source_type" not in host_cols:
        op.alter_column("host", "uid", new_column_name="source_type", existing_type=sa.String())
    cache_cols = [c["name"] for c in inspector.get_columns("cache")]
    if "uid" in cache_cols and "source_type" not in cache_cols:
        op.alter_column("cache", "uid", new_column_name="source_type", existing_type=sa.String())
