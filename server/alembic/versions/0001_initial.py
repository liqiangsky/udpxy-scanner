"""
Initial migration - create all tables from current schema

Revision ID: 0001_initial
Revises: base
Create Date: 2026-01-01
"""
from alembic import op
import sqlalchemy as sa


revision = '0001_initial'
down_revision = 'base'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # parameter table
    op.create_table('parameter',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )

    # config table
    op.create_table('config',
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
    op.create_index('idx_config_enabled', 'config', ['enabled'])

    # subscription table
    op.create_table('subscription',
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
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uid', name='uq_subscription_uid')
    )
    op.create_index('idx_subscription_enabled_cron', 'subscription', ['enabled', 'fetchCron'])

    # cache table
    op.create_table('cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sourceType', sa.String(), nullable=False),
        sa.Column('host', sa.String(), nullable=False),
        sa.Column('geoRegion', sa.String(), nullable=True),
        sa.Column('geoOperator', sa.String(), nullable=True),
        sa.Column('active', sa.Integer(), nullable=True),
        sa.Column('status', sa.Integer(), nullable=True),
        sa.Column('createdAt', sa.Integer(), nullable=True),
        sa.Column('updatedAt', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('host', name='uq_cache_host')
    )
    op.create_index('idx_cache_source_type', 'cache', ['sourceType'])

    # host table
    op.create_table('host',
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
    op.create_index('idx_host_region_operator', 'host', ['region', 'operator'])
    op.create_index('idx_host_geo', 'host', ['geoRegion', 'geoOperator'])
    op.create_index('idx_host_host', 'host', ['host'])
    op.create_index('idx_host_source_type', 'host', ['sourceType'])
    op.create_index('idx_host_geo_region', 'host', ['geoRegion'])
    op.create_index('idx_host_geo_operator', 'host', ['geoOperator'])
    op.create_unique_constraint('uq_host_unique', 'host', ['host', 'target', 'channelName'])

    # notification table
    op.create_table('notification',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('content', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('read', sa.Integer(), nullable=True),
        sa.Column('createdAt', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_notification_read', 'notification', ['read'])
    op.create_index('idx_notification_created', 'notification', ['createdAt'])


def downgrade() -> None:
    op.drop_table('notification')
    op.drop_table('host')
    op.drop_table('cache')
    op.drop_table('subscription')
    op.drop_table('config')
    op.drop_table('parameter')
