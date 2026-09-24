"""add unique constraint on host(host, target, channel_name)

修复换 PostgreSQL 后扫描入库 upsert 报错：
psycopg2.errors.InvalidColumnReference: there is no unique or exclusion
constraint matching the ON CONFLICT specification

SQLite 旧库带该唯一索引，0001/0002 迁移未在 PG 上重建，此迁移幂等补齐。
对已有重复数据先按 updated_at 保留最新一条再去重建索引。

Revision ID: 20260921_04
Revises: 20260921_03
"""
from alembic import op
from sqlalchemy import text


revision = '20260921_04'
down_revision = '20260921_03'

# 与 db.models.Host.__table_args__ 中的约束名保持一致
CONSTRAINT_NAME = 'uq_host_host_target_channel'


def upgrade() -> None:
    conn = op.get_bind()

    already_exists = conn.execute(
        text(
            """
            SELECT 1 FROM pg_constraint
            WHERE conname = :cname
              AND conrelid = 'host'::regclass
            """
        ),
        {"cname": CONSTRAINT_NAME},
    ).fetchone()
    if already_exists:
        return

    # 去重：同 (host, target, channel_name) 只保留 updated_at 最大（次选 id 最大）的一条
    conn.execute(
        text(
            """
            DELETE FROM host a
            USING host b
            WHERE a.host = b.host
              AND a.target = b.target
              AND a.channel_name = b.channel_name
              AND (a.updated_at, a.id) < (b.updated_at, b.id)
            """
        )
    )

    op.create_unique_constraint(
        CONSTRAINT_NAME, 'host', ['host', 'target', 'channel_name']
    )


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_constraint(CONSTRAINT_NAME, 'host', type_='unique')
