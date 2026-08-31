"""
Add type column to subscription table (if missing)

Older databases may not have this column.
Revision ID: 0002_add_subscription_type
Revises: 0001_initial
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa


revision = '0002_add_subscription_type'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 检查 type 列是否已存在，避免重复添加
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col['name'] for col in inspector.get_columns('subscription')]

    if 'type' not in columns:
        op.add_column('subscription', sa.Column('type', sa.String(), nullable=True, server_default='api'))
        # 回填现有记录的 type 值
        op.execute("UPDATE subscription SET type = 'api' WHERE type IS NULL")


def downgrade() -> None:
    op.drop_column('subscription', 'type')
