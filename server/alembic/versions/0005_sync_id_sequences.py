"""sync id sequences to MAX(id)

修复 SQLite -> PostgreSQL 迁移后插入报错：
psycopg2.errors.UniqueViolation: duplicate key value violates
unique constraint "host_pkey" (Key (id)=(743) already exists)

迁移脚本带显式 id 插入数据，但 PG 自增序列不会自动跟进，序列落后于
MAX(id) 时新行拿到已存在的 id 直接撞主键。此迁移对每张带自增主键的表
幂等执行 setval(seq, MAX(id))，可重复执行。

Revision ID: 20260922_05
Revises: 20260921_04
"""
from alembic import op
from sqlalchemy import text


revision = '20260922_05'
down_revision = '20260921_04'


def upgrade() -> None:
    conn = op.get_bind()

    # 所有带 serial/bigserial 默认值的列（information_schema 幂等发现，不写死表名）
    rows = conn.execute(
        text(
            """
            SELECT table_name, column_name FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_default LIKE 'nextval(%'
            """
        )
    ).fetchall()

    for table_name, column_name in rows:
        seq = conn.execute(
            text("SELECT pg_get_serial_sequence(:t, :c)"),
            {"t": table_name, "c": column_name},
        ).scalar()
        if not seq:
            continue
        # 空表 MAX 为 NULL：setval(seq, 1, false)，下个 nextval 从 1 开始
        conn.execute(
            text(
                f"SELECT setval(:seq, COALESCE((SELECT MAX({column_name}) FROM {table_name}), 1), "
                f"(SELECT MAX({column_name}) FROM {table_name}) IS NOT NULL)"
            ),
            {"seq": seq},
        )

    # downgrade 不回退序列：把序列往回拨只会制造主键冲突，无意义


def downgrade() -> None:
    pass
