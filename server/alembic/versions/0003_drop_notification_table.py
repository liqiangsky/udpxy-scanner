"""drop_notification_table

通知模块移除：通知改为 SSE 实时推送 + 后端日志记录，不再落库。
对从未有过 notification 表的全新数据库，此迁移为空操作。

Revision ID: 20260921_03
Revises: 20260921_01
"""
from alembic import op
import sqlalchemy as sa


revision = '20260921_03'
down_revision = '20260921_01'


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'notification' in inspector.get_table_names():
        op.drop_table('notification')


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'notification' not in inspector.get_table_names():
        op.create_table(
            'notification',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('type', sa.String(), nullable=False, server_default='info'),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('content', sa.String(), nullable=True),
            sa.Column('source', sa.String(), nullable=True),
            sa.Column('read', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('created_at', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
