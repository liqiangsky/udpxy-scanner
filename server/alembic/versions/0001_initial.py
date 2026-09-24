"""create_initial_tables

Revision ID: 20260920_01
Revises:
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa


revision = '20260920_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 parameter 表
    op.create_table(
        'parameter',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )

    # 创建 config 表
    op.create_table(
        'config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('dataSource', sa.String(), nullable=False),
        sa.Column('templateRegion', sa.String(), nullable=True),
        sa.Column('templateOperator', sa.String(), nullable=True),
        sa.Column('templateTargetName', sa.String(), nullable=True),
        sa.Column('templateTargetAddress', sa.String(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=True),
        sa.Column('createdAt', sa.Integer(), nullable=True),
        sa.Column('updatedAt', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 创建 subscription 表
    op.create_table(
        'subscription',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('uid', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('type', sa.String(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=True),
        sa.Column('fetchCron', sa.String(), nullable=True),
        sa.Column('lastFetchAt', sa.Integer(), nullable=True),
        sa.Column('createdAt', sa.Integer(), nullable=True),
        sa.Column('updatedAt', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 创建 cache 表
    op.create_table(
        'cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sourceType', sa.String(), nullable=False),
        sa.Column('host', sa.String(), nullable=False),
        sa.Column('geoRegion', sa.String(), nullable=True),
        sa.Column('geoOperator', sa.String(), nullable=True),
        sa.Column('active', sa.Integer(), nullable=True),
        sa.Column('status', sa.Integer(), nullable=True),
        sa.Column('createdAt', sa.Integer(), nullable=True),
        sa.Column('updatedAt', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 创建 host 表
    op.create_table(
        'host',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('host', sa.String(), nullable=False),
        sa.Column('ip', sa.String(), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('sourceType', sa.String(), nullable=True),
        sa.Column('sourceName', sa.String(), nullable=True),
        sa.Column('region', sa.String(), nullable=False),
        sa.Column('operator', sa.String(), nullable=False),
        sa.Column('geoRegion', sa.String(), nullable=True),
        sa.Column('geoOperator', sa.String(), nullable=True),
        sa.Column('delay', sa.Integer(), nullable=False),
        sa.Column('protocol', sa.String(), nullable=False),
        sa.Column('target', sa.String(), nullable=False),
        sa.Column('channelName', sa.String(), nullable=False),
        sa.Column('createdAt', sa.Integer(), nullable=False),
        sa.Column('updatedAt', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # notification 表已移除：通知改为 SSE 实时推送 + 日志记录（见 0003）


def downgrade() -> None:
    op.drop_table('host')
    op.drop_table('cache')
    op.drop_table('subscription')
    op.drop_table('config')
    op.drop_table('parameter')
