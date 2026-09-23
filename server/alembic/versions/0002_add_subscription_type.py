"""add_subscription_type

Revision ID: 20260920_02
Revises: 20260920_01
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa


revision = '20260920_02'
down_revision = '20260920_01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 如果需要添加索引或其他变更，在这里编写
    pass


def downgrade() -> None:
    pass
