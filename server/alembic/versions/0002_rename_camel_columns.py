"""rename_camel_columns

Revision ID: 20260921_01
Revises: 20260920_02
"""
from alembic import op
import sqlalchemy as sa

revision = '20260921_01'
down_revision = '20260920_02'


# (表, 旧驼峰列名, 新蛇形列名, 列类型)
_RENAMES = [
    ('config', 'dataSource', 'data_source', sa.String()),
    ('config', 'templateRegion', 'template_region', sa.String()),
    ('config', 'templateOperator', 'template_operator', sa.String()),
    ('config', 'templateTargetName', 'template_target_name', sa.String()),
    ('config', 'templateTargetAddress', 'template_target_address', sa.String()),
    ('config', 'createdAt', 'created_at', sa.Integer()),
    ('config', 'updatedAt', 'updated_at', sa.Integer()),
    ('subscription', 'fetchCron', 'fetch_cron', sa.String()),
    ('subscription', 'lastFetchAt', 'last_fetch_at', sa.Integer()),
    ('subscription', 'createdAt', 'created_at', sa.Integer()),
    ('subscription', 'updatedAt', 'updated_at', sa.Integer()),
    ('cache', 'sourceType', 'source_type', sa.String()),
    ('cache', 'geoRegion', 'geo_region', sa.String()),
    ('cache', 'geoOperator', 'geo_operator', sa.String()),
    ('cache', 'createdAt', 'created_at', sa.Integer()),
    ('cache', 'updatedAt', 'updated_at', sa.Integer()),
    ('host', 'sourceType', 'source_type', sa.String()),
    ('host', 'sourceName', 'source_name', sa.String()),
    ('host', 'geoRegion', 'geo_region', sa.String()),
    ('host', 'geoOperator', 'geo_operator', sa.String()),
    ('host', 'channelName', 'channel_name', sa.String()),
    ('host', 'createdAt', 'created_at', sa.Integer()),
    ('host', 'updatedAt', 'updated_at', sa.Integer()),
]


def upgrade() -> None:
    for table, old, new, col_type in _RENAMES:
        op.alter_column(
            table, old,
            new_column_name=new,
            existing_type=col_type,
        )


def downgrade() -> None:
    for table, old, new, col_type in _RENAMES:
        op.alter_column(
            table, new,
            new_column_name=old,
            existing_type=col_type,
        )
